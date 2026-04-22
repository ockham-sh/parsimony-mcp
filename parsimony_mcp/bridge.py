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
tables. The encoder is the official ``toon-format`` library.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from mcp.types import TextContent, Tool
from parsimony.connector import Connector
from parsimony.errors import (
    ConnectorError,
    EmptyDataError,
    PaymentRequiredError,
    RateLimitError,
    UnauthorizedError,
)
from parsimony.result import Result
from pydantic import ValidationError
from toon_format import encode

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


def result_to_content(result: Result, max_rows: int = _MAX_ROWS) -> list[TextContent]:
    """Serialize a connector Result to MCP text content as TOON.

    DataFrames render as a tabular block followed by ``total_rows``
    and a ``truncation`` directive when the head is smaller than the
    full result. Series render as a 2-column tabular block. Scalars
    render as a single ``value:`` line.
    """
    data = result.data
    payload: dict[str, Any]
    if isinstance(data, pd.DataFrame):
        total = len(data)
        preview = data.head(max_rows).map(_cap_cell)
        payload = {"preview": preview.to_dict("records")}
        if total > max_rows:
            payload["total_rows"] = total
            payload["truncation"] = (
                f"Discovery preview only — for the full {total} rows, "
                f"load via discover.load_all().bind_env() and call "
                f"connectors['<connector>'](...) in Python. "
                f"Do not call this MCP tool again hoping for more rows."
            )
    elif isinstance(data, pd.Series):
        capped = data.map(_cap_cell)
        payload = {"result": [{"key": str(k), "value": v} for k, v in capped.items()]}
    else:
        payload = {"value": _cap_cell(data) if isinstance(data, str) else data}
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


def translate_error(exc: BaseException, tool_name: str) -> list[TextContent]:
    """Render an exception as agent-safe text content.

    Each branch emits a FIXED user-safe string. ``str(exc)`` is never spliced
    into output, because ``ConnectorError`` subclasses (and the httpx errors
    they wrap) commonly embed request URLs with query-string credentials.
    The agent gets the error class semantics plus the provider name; it does
    not get the raw upstream message.
    """
    if isinstance(exc, ValidationError):
        return _error_content(_format_validation_error(exc, tool_name))
    if isinstance(exc, UnauthorizedError):
        return _error_content(
            f"Authentication error for {exc.provider}. Check that the API key "
            f"env var is configured correctly for this connector; DO NOT retry "
            f"this tool with different arguments."
        )
    if isinstance(exc, PaymentRequiredError):
        return _error_content(
            f"Plan restriction for {exc.provider}: this endpoint requires a "
            f"higher-tier API plan. DO NOT retry this tool; try a different "
            f"connector or inform the user that their current plan cannot "
            f"serve this data."
        )
    if isinstance(exc, RateLimitError):
        if exc.quota_exhausted:
            return _error_content(
                f"Rate limit for {exc.provider}: API quota exhausted for the "
                f"current billing period. DO NOT retry; either use a different "
                f"connector or inform the user to wait for the next billing "
                f"cycle."
            )
        return _error_content(
            f"Rate limit for {exc.provider}: retry after "
            f"{exc.retry_after:.0f} seconds. DO NOT retry this tool "
            f"immediately; pick a different connector, ask the user, or stop."
        )
    if isinstance(exc, EmptyDataError):
        return _error_content(
            f"No data returned from {exc.provider} for the given parameters. "
            f"This is a successful query with an empty result set — the "
            f"parameters likely do not match any records. Adjust parameters "
            f"or try a different connector."
        )
    if isinstance(exc, ConnectorError):
        # ProviderError, ParseError, or the base ConnectorError. Emit the
        # provider name + exception class only — never the raw message.
        return _error_content(
            f"Error from {exc.provider} ({type(exc).__name__}). "
            f"Upstream provider returned an unexpected response."
        )
    # Catch-all — caller (server.call_tool) is expected to log full context
    # before returning this, never log exc here because _logging's JSON
    # formatter omits tracebacks by default and we're relying on that.
    # ``type(exc).__name__`` is a Python class identifier and carries no user
    # data, so exposing it is safe and lets the agent distinguish transient
    # upstream faults (e.g. HTTPStatusError) from local bugs.
    return _error_content(
        f"Internal error in {tool_name} ({type(exc).__name__}); see server logs"
    )


__all__ = ["_cap_cell", "connector_to_tool", "result_to_content", "translate_error"]
