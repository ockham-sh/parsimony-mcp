"""Unit tests for bridge.py — pure-function transformations only.

No MCP Server is constructed in this file; integration coverage lives in
``test_server.py``.
"""

from __future__ import annotations

import pandas as pd
from parsimony.errors import (
    ConnectorError,
    EmptyDataError,
    PaymentRequiredError,
    RateLimitError,
    UnauthorizedError,
)
from parsimony.result import Provenance, Result
from pydantic import BaseModel, Field, ValidationError

from parsimony_mcp.bridge import (
    _MAX_CELL_CHARS,
    _cap_cell,
    connector_to_tool,
    result_to_content,
    translate_error,
)


class TestConnectorToTool:
    def test_name_and_description_preserved(self, tool_connectors):
        tools = [connector_to_tool(c) for c in tool_connectors]
        names = {t.name for t in tools}
        assert "mock_search" in names
        assert "mock_profile" in names

    def test_input_schema_has_properties(self, tool_connectors):
        for c in tool_connectors:
            tool = connector_to_tool(c)
            assert "properties" in tool.inputSchema

    def test_defs_stripped_from_schema(self, tool_connectors):
        for c in tool_connectors:
            tool = connector_to_tool(c)
            assert "$defs" not in tool.inputSchema

    def test_title_stripped_from_schema(self, tool_connectors):
        for c in tool_connectors:
            tool = connector_to_tool(c)
            assert "title" not in tool.inputSchema


class TestResultToContent:
    def test_dataframe_emits_toon_tabular_block(self):
        df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        result = Result(data=df, provenance=Provenance(source="test"))
        content = result_to_content(result)
        assert len(content) == 1
        text = content[0].text
        # TOON header announces the row count and column list.
        assert text.startswith("preview[2]{a,b}:")
        # Rows are indented and comma-separated.
        assert "  1,x" in text
        assert "  2,y" in text

    def test_truncation_emits_total_rows_and_directive_keys(self):
        df = pd.DataFrame({"val": range(100)})
        result = Result(data=df, provenance=Provenance(source="test"))
        content = result_to_content(result, max_rows=10)
        text = content[0].text
        # Header reflects the preview count, not the total.
        assert text.startswith("preview[10]{val}:")
        # Total appears as a top-level TOON key.
        assert "total_rows: 100" in text
        # Truncation directive names the Python escape hatch and closes
        # the retry door — these strings are agent-loop control.
        assert "discover.load_all().bind_env()" in text
        assert "connectors[" in text
        assert "Discovery preview only" in text
        assert "Do not call this MCP tool again hoping for more rows" in text

    def test_no_truncation_keys_below_max_rows(self):
        df = pd.DataFrame({"val": range(5)})
        result = Result(data=df, provenance=Provenance(source="test"))
        content = result_to_content(result, max_rows=50)
        text = content[0].text
        assert "total_rows:" not in text
        assert "truncation:" not in text

    def test_string_data_emits_value_kv_line(self):
        result = Result(data="hello world", provenance=Provenance(source="test"))
        content = result_to_content(result)
        assert content[0].text == "value: hello world"

    def test_string_with_special_chars_is_quoted(self):
        result = Result(data="hello, world", provenance=Provenance(source="test"))
        content = result_to_content(result)
        assert content[0].text == 'value: "hello, world"'

    def test_series_emits_two_column_tabular_block(self):
        s = pd.Series({"name": "Test", "value": 42})
        result = Result(data=s, provenance=Provenance(source="test"))
        content = result_to_content(result)
        text = content[0].text
        assert text.startswith("result[2]{key,value}:")
        assert "name,Test" in text
        assert "value,42" in text

    def test_compromised_upstream_cell_quoted_not_injected(self):
        """A cell with a newline / comma / SYSTEM marker must not break out of its row."""
        df = pd.DataFrame({"a": ["safe\nfake_row,fake_value"]})
        result = Result(data=df, provenance=Provenance(source="test"))
        content = result_to_content(result)
        text = content[0].text
        # Header announces exactly one row regardless of the cell content.
        assert text.startswith("preview[1]{a}:")
        # The cell is quoted AND the newline is escaped to ``\n`` (two chars,
        # backslash + n) so no real newline can break the TOON row layout.
        assert '"safe\\nfake_row,fake_value"' in text
        # No raw newline leaks out of the quoted cell into the row stream
        # (only the trailing newline at end-of-cell is allowed).
        body = text.split("preview[1]{a}:\n", 1)[1]
        assert "\n" not in body  # exactly one row, no embedded newlines

    def test_dataframe_with_long_string_truncated_in_preview(self):
        """A 10000-character cell from an upstream is bounded to ~500 chars."""
        long = "x" * 10_000
        df = pd.DataFrame({"a": [long]})
        result = Result(data=df, provenance=Provenance(source="test"))
        text = result_to_content(result)[0].text
        assert long not in text
        assert "…" in text


class TestCapCell:
    def test_short_string_passes_through(self):
        assert _cap_cell("abc") == "abc"

    def test_long_string_truncated_to_max_chars(self):
        long = "x" * 600
        capped = _cap_cell(long, max_chars=500)
        assert isinstance(capped, str)
        assert len(capped) == 500
        assert capped.endswith("…")

    def test_default_cap_is_500(self):
        assert _MAX_CELL_CHARS == 500
        assert len(_cap_cell("y" * 10_000)) == 500

    def test_int_passes_through(self):
        assert _cap_cell(42) == 42

    def test_none_passes_through(self):
        assert _cap_cell(None) is None


class _ArgsModel(BaseModel):
    query: str = Field(..., min_length=1)
    count: int = Field(default=1, ge=1)


class TestTranslateError:
    """Bridge-side rendering tests.

    The agent-facing prose for ``ConnectorError`` subclasses is locked in
    ``parsimony/tests/test_errors.py`` (kernel default messages).  These
    tests assert only the bridge's contract: ``[tool_name]`` prefix is
    added, ``str(exc)`` is rendered for ConnectorError, ValidationError
    is custom-formatted, and unknown exceptions never expose ``str(exc)``.
    """

    # ── ValidationError ──────────────────────────────────────────────

    def test_validation_error_omits_input_value(self):
        """Critical: Pydantic default str(exc) leaks input_value which may be a secret."""
        try:
            _ArgsModel.model_validate({"query": "sk-secret-key", "count": -1})
        except ValidationError as exc:
            content = translate_error(exc, "some_tool")
            text = content[0].text
            # The field name must appear; the secret value must not.
            assert "query" in text or "count" in text
            assert "sk-secret-key" not in text

    def test_validation_error_announces_invalid_parameters(self):
        try:
            _ArgsModel.model_validate({})
        except ValidationError as exc:
            content = translate_error(exc, "some_tool")
            assert "Invalid parameters" in content[0].text

    # ── ConnectorError rendering ─────────────────────────────────────

    def test_connector_error_includes_tool_name_prefix(self):
        """Bridge wraps str(exc) with `[tool_name]` for agent context."""
        exc = UnauthorizedError(provider="fred", env_var="FRED_API_KEY")
        content = translate_error(exc, "fred_fetch")
        text = content[0].text
        assert text.startswith("[fred_fetch] ")

    def test_connector_error_renders_str_exc_verbatim(self):
        """The kernel default message reaches the agent unmodified after the prefix."""
        exc = UnauthorizedError(provider="fred", env_var="FRED_API_KEY")
        text = translate_error(exc, "fred_fetch")[0].text
        assert text == f"[fred_fetch] {exc}"

    def test_connector_error_subclasses_all_render_via_str(self):
        """Every typed subclass must round-trip through `str(exc)`."""
        cases = [
            UnauthorizedError(provider="fred"),
            UnauthorizedError(provider="fred", env_var="FRED_API_KEY"),
            PaymentRequiredError(provider="premium"),
            RateLimitError(provider="fast", retry_after=30.0),
            RateLimitError(provider="q", retry_after=0.0, quota_exhausted=True),
            EmptyDataError(provider="e"),
            ConnectorError("flow_id must be non-empty", provider="sdmx"),
        ]
        for exc in cases:
            content = translate_error(exc, "tool")
            assert content[0].text == f"[tool] {exc}"

    def test_bare_connector_error_passes_author_message_through(self):
        """The bare ConnectorError contract: author-supplied message is the agent string."""
        exc = ConnectorError("Set PARSIMONY_X to enable this tool", provider="x")
        text = translate_error(exc, "x_search")[0].text
        assert text == "[x_search] Set PARSIMONY_X to enable this tool"

    # ── Unknown Exception fallback ───────────────────────────────────

    def test_unknown_exception_returns_safe_fallback(self):
        exc = RuntimeError("unexpected")
        content = translate_error(exc, "mystery_tool")
        text = content[0].text
        assert "Internal error" in text
        assert "mystery_tool" in text
        # Class name appears so the agent can distinguish upstream faults
        # from local bugs; the raw message (which could embed secrets) does not.
        assert "RuntimeError" in text
        assert "unexpected" not in text

    def test_unknown_exception_does_not_leak_url_with_api_key(self):
        """Class name is safe; str(exc) for httpx-style errors is not."""

        class HTTPStatusError(Exception):
            """Mimics httpx.HTTPStatusError whose message embeds the full URL."""

        raw = (
            "Server error '500 Internal Server Error' for url "
            "'https://api.stlouisfed.org/fred/series/search?api_key=REAL_KEY&search_text=x'"
        )
        exc = HTTPStatusError(raw)
        content = translate_error(exc, "fred_search")
        text = content[0].text
        assert "HTTPStatusError" in text
        assert "REAL_KEY" not in text
        assert "api_key=" not in text
        assert "api.stlouisfed.org" not in text
