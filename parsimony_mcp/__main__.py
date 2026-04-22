"""Entry point: ``parsimony-mcp`` (or ``python -m parsimony_mcp``).

Dispatch model:

* Bare ``parsimony-mcp`` (no args, or only server-relevant args) runs
  the MCP stdio server. This is load-bearing: existing ``.mcp.json``
  entries configured as ``{"command": "parsimony-mcp"}`` must keep
  working after we add subcommands. DO NOT rename this path to a
  ``serve`` subcommand.
* ``parsimony-mcp init [...]`` dispatches to :mod:`parsimony_mcp.cli.init`.
* Future subcommands slot in as additional branches — one entry
  point, argparse dispatch, no parallel console scripts.

Console scripts cannot reference coroutines directly, so :func:`main` is
the synchronous zero-arg entry point that wraps :func:`_run` in
``asyncio.run``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import mcp.server.stdio
from parsimony import discover

from parsimony_mcp import init as init_command
from parsimony_mcp._env import load_env
from parsimony_mcp._logging import configure_logging
from parsimony_mcp.server import create_server

logger = logging.getLogger("parsimony_mcp.main")

_SLOW_DISCOVERY_MS = 2000

_KNOWN_SUBCOMMANDS = frozenset({"init"})


def _load_env_from_environment() -> None:
    """Apply the .env precedence chain to ``os.environ`` before discovery.

    Sequence is load-bearing — configuration sources must load in the
    order their consumers read them:

    1. ``load_env`` runs first so ``.env`` and any caller-provided
       overrides are visible by the time
    2. ``configure_logging`` reads ``PARSIMONY_MCP_LOG_LEVEL`` and
    3. ``discover.load_all().bind_env()`` snapshots the rest of the env
       vars at bind time.

    Reordering breaks ``.env``-driven config silently (the level
    override or the API key both vanish).
    """
    project_dir_pin_str = os.environ.get("PARSIMONY_MCP_PROJECT_DIR")
    project_dir_pin = Path(project_dir_pin_str) if project_dir_pin_str else None
    load_env(cwd=Path.cwd(), project_dir_pin=project_dir_pin)


def _warn_unbound(all_connectors: object) -> None:
    """Log a WARNING for every connector with unresolved env vars.

    ``discover.load_all().bind_env()`` keeps unbound connectors in the
    collection (see the kernel design doc scenario §2). The adapter is
    the highest-visibility surface for the user to notice missing
    credentials — the MCP log pane shows these on boot, naming the env
    vars the user is expected to set. Without this, an unbound tool
    silently returns ``UnauthorizedError`` only when the agent picks it
    up.
    """
    unbound = getattr(all_connectors, "unbound", ())
    for name in unbound:
        conn = all_connectors.get(name) if hasattr(all_connectors, "get") else None
        env_vars = sorted(conn.env_map.values()) if conn is not None and conn.env_map else []
        logger.warning(
            "connector %s is unbound — set %s in env or .env",
            name,
            ", ".join(env_vars) if env_vars else "<no env_map declared>",
            extra={"connector": name, "env_vars": env_vars},
        )


async def _run_server() -> None:
    _load_env_from_environment()
    configure_logging()

    start = time.monotonic()
    all_connectors = discover.load_all().bind_env()
    discovery_ms = int((time.monotonic() - start) * 1000)

    tool_connectors = all_connectors.filter(tags=["tool"])
    count = len(list(tool_connectors))

    _warn_unbound(all_connectors)

    if count == 0:
        logger.warning(
            "parsimony-mcp started with 0 connectors tagged 'tool'; install a plugin "
            "(e.g. `pip install parsimony-fred`) to populate the tool catalog",
            extra={"discovery_ms": discovery_ms},
        )
    else:
        logger.info(
            "loaded connectors",
            extra={"count": count, "discovery_ms": discovery_ms},
        )

    if discovery_ms > _SLOW_DISCOVERY_MS:
        logger.warning(
            "slow plugin discovery — check for plugins with heavy eager imports",
            extra={"discovery_ms": discovery_ms, "threshold_ms": _SLOW_DISCOVERY_MS},
        )

    server = create_server(all_connectors)
    async with mcp.server.stdio.stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def _dispatch(argv: Sequence[str]) -> int:
    """Route ``argv`` to the server or a subcommand.

    A subcommand is the first positional argument if it matches
    :data:`_KNOWN_SUBCOMMANDS`. Anything else (empty ``argv``, or
    unknown first token) keeps the existing stdio-server behaviour,
    so legacy launchers that pass flags to the server don't regress.
    """
    if argv and argv[0] in _KNOWN_SUBCOMMANDS:
        sub = argv[0]
        rest = argv[1:]
        if sub == "init":
            return init_command.run(rest)
        # Unreachable: _KNOWN_SUBCOMMANDS is a closed set.
        raise AssertionError(f"no dispatch for subcommand {sub!r}")

    try:
        asyncio.run(_run_server())
    except KeyboardInterrupt:
        return 130  # SIGINT — Python's default handler exit code.
    return int(init_command.ExitCode.OK)


def main() -> None:
    """Synchronous console-script entry point."""
    try:
        code = _dispatch(sys.argv[1:])
    except KeyboardInterrupt:
        code = 130
    sys.exit(code)


if __name__ == "__main__":
    main()
