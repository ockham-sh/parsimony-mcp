"""Bounded ``.env`` loader with explicit precedence.

The MCP server reads connector credentials from three sources, in
strict precedence order:

1. **Programmatic overrides** — the ``overrides`` argument to
   :func:`load_env`, used by embedders that build the server in their
   own process and want to inject credentials without touching the
   filesystem.
2. **Pre-existing ``os.environ``** — populated either by the user's
   shell or by an MCP host's ``mcpServers.*.env`` block at child-
   process spawn time. This is the security-preferred path; a
   credential here means the host already vetted it.
3. **``.env`` file values** — loaded via ``python-dotenv`` with
   ``override=False`` so anything already in ``os.environ`` wins.

The walk that locates the ``.env`` file is bounded for security.
Without bounds, ``python-dotenv``'s default upward walk would happily
load ``/tmp/.env`` or ``~/.env`` if the developer happened to run from
a deep subdirectory of those — the natural consequence is that an
attacker who can drop a ``.env`` somewhere in the ancestor chain
silently wins the precedence race over the project's intended
credentials.

The bounds:

* Stop at the first directory containing ``.git``, ``pyproject.toml``,
  or ``.mcp.json`` — these are project-root anchors.
* Never ascend past ``$HOME``.
* Refuse to read a ``.env`` whose containing directory is
  world-writable (mode bit ``0o002``).

``PARSIMONY_MCP_PROJECT_DIR`` is honoured as an explicit pin, but
only after passing the same trust checks: must resolve strictly to a
real directory, owned by the current uid, not world-writable, and
not escape ``$HOME``. Any failure logs a warning and falls back to
the bounded upward walk — we never silently succeed with an attacker-
chosen directory.

The function mutates ``os.environ`` because the kernel's
:meth:`parsimony.connector.Connectors.bind_env` snapshots env vars at
bind time. The returned ``MappingProxyType`` is a read-only snapshot of
the post-load environment for inspection and testing; it is not the
runtime configuration source.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from dotenv import load_dotenv

logger = logging.getLogger("parsimony_mcp.env")

_ANCHOR_FILES = (".git", "pyproject.toml", ".mcp.json")

# Re-export python-dotenv's ``load_dotenv`` under our public surface so
# callers can ``from parsimony_mcp._env import load_dotenv``. ``.env``
# autoload lives in this adapter rather than the kernel because the kernel
# stays free of process-level filesystem side effects.
__all__ = ["load_dotenv", "load_env"]


def load_env(
    cwd: Path,
    *,
    project_dir_pin: Path | None = None,
    overrides: Mapping[str, str] | None = None,
) -> Mapping[str, str]:
    """Resolve the secrets precedence chain and apply to ``os.environ``.

    Parameters
    ----------
    cwd
        The working directory the bounded walk starts from. Pass
        ``Path.cwd()`` from the entry point.
    project_dir_pin
        Explicit pin for the search root, typically sourced from the
        ``PARSIMONY_MCP_PROJECT_DIR`` env var. If provided and trusted,
        the walk starts here instead of ``cwd``. Untrusted pins are
        rejected with a stderr warning and the walk falls back to
        ``cwd``.
    overrides
        Programmatic overrides applied AFTER ``.env`` is loaded so
        embedders can guarantee certain values regardless of file or
        host state. ``overrides`` win even over pre-existing
        ``os.environ`` entries.

    Returns
    -------
    Mapping[str, str]
        A read-only ``MappingProxyType`` snapshot of ``os.environ``
        after all sources have been applied. Useful for tests and
        logging; the runtime source of truth remains ``os.environ``.
    """
    search_root = _resolve_search_root(cwd, project_dir_pin)
    env_path = _find_env_file(search_root)
    if env_path is not None:
        load_dotenv(env_path, override=False)
        logger.info("loaded .env", extra={"path": str(env_path)})

    if overrides:
        for key, value in overrides.items():
            os.environ[key] = value

    return MappingProxyType(dict(os.environ))


def _resolve_search_root(cwd: Path, pin: Path | None) -> Path:
    """Validate the optional ``PARSIMONY_MCP_PROJECT_DIR`` pin.

    Returns the validated pin if trustworthy, else falls back to
    ``cwd`` with a stderr warning naming the failure mode. Never
    raises — the env loader's contract is best-effort.
    """
    if pin is None:
        return cwd.resolve()
    try:
        resolved = pin.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        _warn_pin_rejected(pin, f"does not resolve: {exc}")
        return cwd.resolve()

    if not resolved.is_dir():
        _warn_pin_rejected(pin, "is not a directory")
        return cwd.resolve()

    if _is_world_writable(resolved):
        _warn_pin_rejected(pin, "directory is world-writable")
        return cwd.resolve()

    if not _is_owned_by_current_user(resolved):
        _warn_pin_rejected(pin, "directory is not owned by the current user")
        return cwd.resolve()

    if not _is_under_home(resolved):
        _warn_pin_rejected(pin, f"resolves outside $HOME: {resolved}")
        return cwd.resolve()

    return resolved


def _find_env_file(search_root: Path) -> Path | None:
    """Walk upward from ``search_root`` looking for a trustworthy ``.env``.

    Stops at the first project-anchor directory (one containing
    ``.git``, ``pyproject.toml``, or ``.mcp.json``) and at ``$HOME``.
    Refuses ``.env`` files whose containing directory is world-
    writable.
    """
    home = _home_resolved()
    if not _is_under_home(search_root):
        # Refuse to walk if we're already outside $HOME — e.g.
        # invoked from /tmp, where any ancestor .env is suspect.
        return None

    for directory in (search_root, *search_root.parents):
        candidate = directory / ".env"
        if candidate.is_file():
            if _is_world_writable(directory):
                _warn_env_rejected(candidate, "containing directory is world-writable")
                return None
            return candidate
        if any((directory / marker).exists() for marker in _ANCHOR_FILES):
            # We've reached a project root with no .env at this level —
            # stop walking so we don't pick up a stale ancestor file.
            return None
        if directory == home:
            break
    return None


def _home_resolved() -> Path:
    """Resolve ``$HOME`` once. Read on every call so monkeypatched tests work."""
    return Path.home().resolve()


def _is_under_home(path: Path) -> bool:
    """Return True iff ``path`` is at or below ``$HOME``."""
    home = _home_resolved()
    try:
        path.relative_to(home)
    except ValueError:
        return False
    return True


def _is_world_writable(path: Path) -> bool:
    """Return True iff ``path``'s mode bits include world-writable."""
    try:
        return bool(path.stat().st_mode & 0o002)
    except OSError:
        # A directory we can't stat is not one we should trust.
        return True


def _is_owned_by_current_user(path: Path) -> bool:
    """Return True iff ``path``'s uid matches the current process uid.

    Returns True on platforms without ``os.getuid`` (Windows) — the
    POSIX ownership concept does not apply there and we fall back to
    trusting the path. Hunt's threat model for this guard is the
    multi-user POSIX system; Windows single-user laptops aren't the
    target.
    """
    getuid = getattr(os, "getuid", None)
    if getuid is None:
        return True
    try:
        return bool(path.stat().st_uid == getuid())
    except OSError:
        return False


def _warn_pin_rejected(pin: Path, reason: str) -> None:
    print(
        f"warning: PARSIMONY_MCP_PROJECT_DIR rejected ({reason}): {pin}; "
        f"falling back to bounded upward walk from CWD",
        file=sys.stderr,
    )


def _warn_env_rejected(path: Path, reason: str) -> None:
    print(f"warning: refusing to load .env at {path} ({reason})", file=sys.stderr)
