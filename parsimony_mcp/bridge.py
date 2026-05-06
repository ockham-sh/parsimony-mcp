"""Bridge between parsimony Connector interface and MCP Tool definitions.

Three responsibilities — all pure, all side-effect free:

1. :func:`connector_to_tool` — map a :class:`parsimony.connector.Connector`
   to an MCP :class:`~mcp.types.Tool` definition.
2. :func:`result_to_content` — serialize a parsimony :class:`Result` to MCP
   text content as TOON (Token-Oriented Object Notation), with a
   self-describing truncation directive.
3. :func:`translate_error` — translate a connector or validation error into
   agent-safe :class:`~mcp.types.TextContent` blocks. Never stringifies the
   raw exception, because raw exception messages routinely embed full
   request URLs including ``?api_key=...`` query-string secrets.

The output format is TOON rather than Markdown because (a) Markdown
table cells need defensive escaping for ``|``, backticks, and
newlines (any of which can break the table or inject host-level
prose) while TOON's CSV-style row format only needs quoting for
structural characters that are easier to reason about; and (b)
TOON's tabular form spends column names once in a header rather
than once per row, saving 30-50% of tokens for typical preview
tables. The encoder is the Rust-backed ``toons`` library.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from mcp.types import TextContent, Tool
from parsimony.connector import Connector
from parsimony.errors import ConnectorError
from parsimony.result import REDACTED, SECRET_NAME_PATTERN, Provenance, Result
from pydantic import ValidationError
from toons import dumps as encode

_MAX_ROWS = 50
_MAX_VALIDATION_ERRORS = 5
_MAX_CELL_CHARS = 500


def _cap_cell(value: Any, max_chars: int = _MAX_CELL_CHARS) -> Any:
    """Truncate string cells so a single rogue upstream value can't blow the
    agent's context budget. Non-strings pass through unchanged."""
    if isinstance(value, str) and len(value) > max_chars:
        return value[: max_chars - 1] + "…"
    return value


def connector_to_tool(conn: Connector) -> Tool:
    """Map a Connector to an MCP Tool definition."""
    schema: dict[str, Any] = dict(conn.param_schema)
    # Strip Pydantic $defs — MCP clients may not support JSON Schema $ref
    schema.pop("$defs", None)
    schema.pop("title", None)
    return Tool(
        name=conn.name,
        description=conn.description,
        inputSchema=schema,
    )


def _provenance_envelope(provenance: Provenance) -> dict[str, Any] | None:
    """Wire-safe provenance dict, or ``None`` when there is no source to report."""
    if not provenance.source:
        return None
    raw = provenance.safe_dump()
    return {k: v for k, v in raw.items() if v not in (None, {}, "", [])}


def _build_data_block(data: Any, max_rows: int) -> dict[str, Any]:
    """Render a connector's ``data`` value into the envelope's data block."""
    if isinstance(data, pd.DataFrame):
        total = len(data)
        preview = data.head(max_rows).map(_cap_cell)
        out: dict[str, Any] = {"preview": preview.to_dict("records")}
        if total > max_rows:
            out["total_rows"] = total
            out["truncation"] = (
                f"Discovery preview only — for the full {total} rows, "
                f"load via discover.load_all().bind_env() and call "
                f"connectors['<connector>'](...) in Python. "
                f"Do not call this MCP tool again hoping for more rows."
            )
        return out
    if isinstance(data, pd.Series):
        capped = data.map(_cap_cell)
        return {"result": [{"key": str(k), "value": v} for k, v in capped.items()]}
    return {"value": _cap_cell(data) if isinstance(data, str) else data}


def result_to_content(result: Result, max_rows: int = _MAX_ROWS) -> list[TextContent]:
    """Serialize a connector Result to a single MCP TOON envelope ``{provenance, data}``."""
    payload: dict[str, Any] = {}
    envelope = _provenance_envelope(result.provenance)
    if envelope is not None:
        payload["provenance"] = envelope
    payload["data"] = _build_data_block(result.data, max_rows)
    return [TextContent(type="text", text=encode(payload))]


def _error_content(message: str) -> list[TextContent]:
    return [TextContent(type="text", text=message)]


def _format_validation_error(exc: ValidationError, tool_name: str) -> str:
    errors = exc.errors()
    head = errors[:_MAX_VALIDATION_ERRORS]
    # Never include input_value — the user may have typed an API key into
    # the agent, and Pydantic's default stringification would round-trip it
    # through the LLM transcript.
    lines = [f"{'.'.join(str(p) for p in err.get('loc', ()))}: {err.get('msg', 'invalid')}" for err in head]
    extra = len(errors) - len(head)
    suffix = f" (+{extra} more)" if extra > 0 else ""
    return f"Invalid parameters for {tool_name}: " + "; ".join(lines) + suffix


def translate_error(
    exc: BaseException,
    tool_name: str,
    *,
    call_params: dict[str, Any] | None = None,
) -> list[TextContent]:
    """Render an exception as agent-safe text content.

    The agent-facing prose for ``ConnectorError`` subclasses lives in
    :mod:`parsimony.errors` — each kernel default message embeds the
    class semantics plus the appropriate agent-loop directive. This
    bridge faithfully renders ``str(exc)`` for those classes; the locked
    contract lives in ``parsimony/tests/test_errors.py``.

    For ``ValidationError`` we build a custom string locally because
    Pydantic's default ``__str__`` includes ``input_value=`` which can
    round-trip user-typed secrets through the LLM transcript. For all
    other exceptions we emit only ``type(exc).__name__`` — the cause
    chain on httpx-wrapped errors carries bearer tokens and request URLs,
    so ``str(exc)`` / interpolation of ``exc`` is forbidden in this
    branch (enforced by ``tests/test_secret_leakage_guards.py``).

    When *call_params* is supplied, the connector and unknown-exception
    branches return a TOON envelope ``{"error": "...", "call": {"tool":
    ..., "params": {...}}}`` with secret-named param values redacted via
    :data:`SECRET_NAME_PATTERN`. ``ValidationError`` keeps the plain-text
    path because its input is unvalidated and may carry malformed values.
    """
    if isinstance(exc, ValidationError):
        return _error_content(_format_validation_error(exc, tool_name))
    if isinstance(exc, ConnectorError):
        message = f"[{tool_name}] {exc}"
    else:
        message = f"Internal error in {tool_name} ({type(exc).__name__}); see server logs"
    if call_params is None:
        return _error_content(message)
    redacted = {
        k: (REDACTED if SECRET_NAME_PATTERN.search(k) else v)
        for k, v in call_params.items()
    }
    payload = {"error": message, "call": {"tool": tool_name, "params": redacted}}
    return [TextContent(type="text", text=encode(payload))]


__all__ = ["_cap_cell", "connector_to_tool", "result_to_content", "translate_error"]
