"""CI guard against patterns that historically leak bearer tokens.

When a connector raises through wrapped httpx exceptions, the request
URL — including ``?api_key=...`` query-string credentials — is
embedded in the exception message AND in the ``__cause__`` /
``__context__`` chain. Three patterns leak them through to the agent
transcript or stderr logs:

1. ``logger.exception(...)`` — emits the full traceback chain.
2. ``traceback.format_exc()`` / ``traceback.print_exc()`` — same.
3. ``f"... {exc}"`` or ``str(exc)`` for *unknown* exception types
   (the catch-all branch). The current code uses ``type(exc).__name__``
   instead, which is a Python class identifier and carries no user data.

This file scans ``server.py`` and ``bridge.py`` for patterns 1 and 2 —
both are unconditional vetoes. Pattern 3 is harder to mechanically
verify (a ``{exc}`` interpolation of a ``TypeError`` from "Missing
params" is safe; the same interpolation of a ``ConnectorError`` is
not), so it stays a code-review concern, but the existing code
demonstrates the safe pattern (``type(exc).__name__``) and the
test_agent_contract.py suite catches regressions on the public
strings.

If a future PR genuinely needs ``logger.exception`` (for an internal
debug-only logger that never flows into MCP responses), add a per-call
``# noqa`` and explain the reasoning. This file deliberately requires
that explicit acknowledgement.
"""

from __future__ import annotations

from pathlib import Path

import parsimony_mcp


def _guarded_module_paths() -> list[Path]:
    """The two modules whose code paths can flow into MCP responses."""
    pkg_dir = Path(parsimony_mcp.__file__).parent
    return [pkg_dir / "server.py", pkg_dir / "bridge.py"]


class TestNoSecretLeakingPatterns:
    """Forbid the two patterns that emit the full exception chain."""

    def test_no_logger_exception(self) -> None:
        for path in _guarded_module_paths():
            text = path.read_text(encoding="utf-8")
            # Strip leading whitespace from each line so that an
            # accidental indented `logger.exception(` is still caught.
            stripped = "\n".join(line.lstrip() for line in text.splitlines())
            assert "logger.exception(" not in stripped, (
                f"{path.name}: logger.exception emits the full traceback "
                f"chain (including __cause__/__context__) which routinely "
                f"contains bearer tokens from wrapped httpx errors. Use "
                f"logger.error with extra={{'exc_type': type(exc).__name__}} "
                f"instead. If you genuinely need it, add # noqa with a "
                f"reasoned comment."
            )

    def test_no_traceback_format_exc(self) -> None:
        for path in _guarded_module_paths():
            text = path.read_text(encoding="utf-8")
            assert "traceback.format_exc" not in text, (
                f"{path.name}: traceback.format_exc serializes the full "
                f"exception chain including bearer tokens carried by "
                f"wrapped httpx errors. Use type(exc).__name__ for the "
                f"agent-facing payload and skip traceback formatting "
                f"entirely."
            )
            assert "traceback.print_exc" not in text, (
                f"{path.name}: traceback.print_exc writes the full exception "
                f"chain to stderr which the MCP host captures into "
                f"transcript logs. Same secret-leakage risk as format_exc."
            )

    def test_translate_error_uses_safe_class_name_pattern(self) -> None:
        """The bridge surfaces exception classes via type(exc).__name__, not str(exc).

        AST-walks translate_error so the docstring's literal string
        "``str(exc)`` is never spliced" doesn't false-positive a naive
        substring grep. Catches the most likely regression: a future PR
        that "simplifies" the catch-all branch to inline str(exc) for
        ConnectorError or the generic Exception arm.
        """
        import ast

        from parsimony_mcp import bridge

        bridge_text = Path(bridge.__file__).read_text(encoding="utf-8")
        tree = ast.parse(bridge_text)
        translate_error_func = next(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == "translate_error"
            ),
            None,
        )
        assert translate_error_func is not None, "translate_error not found in bridge.py"

        # Walk the function body (skipping the docstring) for any
        # str(exc) call or {exc} f-string interpolation.
        body_nodes = translate_error_func.body
        if (
            body_nodes
            and isinstance(body_nodes[0], ast.Expr)
            and isinstance(body_nodes[0].value, ast.Constant)
            and isinstance(body_nodes[0].value.value, str)
        ):
            body_nodes = body_nodes[1:]  # drop docstring

        for node in body_nodes:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    func = sub.func
                    if isinstance(func, ast.Name) and func.id == "str" and sub.args:
                        arg = sub.args[0]
                        if isinstance(arg, ast.Name) and arg.id in {"exc", "e", "exception"}:
                            raise AssertionError(
                                "translate_error must not call str() on caught exceptions; "
                                "wrapped httpx errors carry bearer tokens in their message. "
                                "Use type(exc).__name__ for safe agent-facing surfacing."
                            )
                if isinstance(sub, ast.FormattedValue):
                    val = sub.value
                    if isinstance(val, ast.Name) and val.id in {"exc", "e", "exception"}:
                        raise AssertionError(
                            "translate_error must not f-string-interpolate caught exceptions; "
                            "wrapped httpx errors carry bearer tokens. Use type(exc).__name__."
                        )
