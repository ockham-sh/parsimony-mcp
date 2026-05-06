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
        result = Result(data=df, provenance=Provenance(source="test", source_description="test"))
        content = result_to_content(result)
        assert len(content) == 1
        text = content[0].text
        assert "data:" in text
        assert "preview[2]{a,b}:" in text
        assert "  1,x" in text
        assert "  2,y" in text

    def test_truncation_emits_total_rows_and_directive_keys(self):
        df = pd.DataFrame({"val": range(100)})
        result = Result(data=df, provenance=Provenance(source="test", source_description="test"))
        text = result_to_content(result, max_rows=10)[0].text
        assert "preview[10]{val}:" in text
        assert "total_rows: 100" in text
        assert "discover.load_all().bind_env()" in text
        assert "connectors[" in text
        assert "Discovery preview only" in text
        assert "Do not call this MCP tool again hoping for more rows" in text

    def test_no_truncation_keys_below_max_rows(self):
        df = pd.DataFrame({"val": range(5)})
        result = Result(data=df, provenance=Provenance(source="test", source_description="test"))
        text = result_to_content(result, max_rows=50)[0].text
        assert "total_rows:" not in text
        assert "truncation:" not in text

    def test_string_data_emits_value_kv_line(self):
        result = Result(data="hello world", provenance=Provenance(source="test", source_description="test"))
        text = result_to_content(result)[0].text
        assert "value: hello world" in text

    def test_string_with_special_chars_is_quoted(self):
        result = Result(data="hello, world", provenance=Provenance(source="test", source_description="test"))
        text = result_to_content(result)[0].text
        assert 'value: "hello, world"' in text

    def test_series_emits_two_column_tabular_block(self):
        s = pd.Series({"name": "Test", "value": 42})
        result = Result(data=s, provenance=Provenance(source="test", source_description="test"))
        text = result_to_content(result)[0].text
        assert "result[2]{key,value}:" in text
        assert "name,Test" in text
        assert "value,42" in text

    def test_compromised_upstream_cell_quoted_not_injected(self):
        df = pd.DataFrame({"a": ["safe\nfake_row,fake_value"]})
        result = Result(data=df, provenance=Provenance(source="test", source_description="test"))
        text = result_to_content(result)[0].text
        assert "preview[1]{a}:" in text
        assert '"safe\\nfake_row,fake_value"' in text

    def test_dataframe_with_long_string_truncated_in_preview(self):
        long = "x" * 10_000
        df = pd.DataFrame({"a": [long]})
        result = Result(data=df, provenance=Provenance(source="test", source_description="test"))
        text = result_to_content(result)[0].text
        assert long not in text
        assert "…" in text


class TestProvenanceBlock:
    def test_provenance_keyed_in_envelope_when_present(self):
        df = pd.DataFrame({"a": [1]})
        result = Result(
            data=df,
            provenance=Provenance(source="fred", source_description="fred", params={"series_id": "GDPC1"}),
        )
        content = result_to_content(result)
        assert len(content) == 1
        text = content[0].text
        assert text.startswith("provenance:")
        assert "fred" in text
        assert "GDPC1" in text
        assert "data:" in text

    def test_empty_provenance_emits_no_provenance_key(self):
        df = pd.DataFrame({"a": [1]})
        result = Result(data=df)
        content = result_to_content(result)
        assert len(content) == 1
        text = content[0].text
        assert "provenance:" not in text
        assert "data:" in text

    def test_provenance_redacts_secret_shaped_param_keys(self):
        df = pd.DataFrame({"a": [1]})
        result = Result(
            data=df,
            provenance=Provenance(
                source="evil",
                source_description="evil source",
                params={"api_key": "sk-leaked", "Token": "t-leaked", "ok": "fine"},
            ),
        )
        text = result_to_content(result)[0].text
        assert "sk-leaked" not in text
        assert "t-leaked" not in text
        assert "«redacted»" in text
        assert "fine" in text

    def test_provenance_caps_huge_properties_payload(self):
        df = pd.DataFrame({"a": [1]})
        bloat = {f"k{i}": "v" * 200 for i in range(50)}
        result = Result(
            data=df,
            provenance=Provenance(source="bloat", source_description="bloat", properties=bloat),
        )
        text = result_to_content(result)[0].text
        assert "truncated: true" in text
        assert "byte_length:" in text
        assert "field: properties" in text
        assert "vvvvvvvvvv" not in text


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


class TestTranslateErrorCallEnvelope:
    def test_call_envelope_carries_tool_name_and_params(self):
        from parsimony.errors import EmptyDataError

        exc = EmptyDataError(provider="fred", message="no rows")
        content = translate_error(exc, "fred_fetch", call_params={"series_id": "GDPC1"})
        text = content[0].text
        assert "error:" in text
        assert "[fred_fetch] no rows" in text
        assert "call:" in text
        assert "tool: fred_fetch" in text
        assert "GDPC1" in text

    def test_call_envelope_redacts_secret_shaped_keys(self):
        from parsimony.errors import EmptyDataError

        exc = EmptyDataError(provider="x", message="no rows")
        params = {"api_key": "sk-leaked", "Token": "t-leaked", "series_id": "GDPC1"}
        text = translate_error(exc, "x_tool", call_params=params)[0].text
        assert "sk-leaked" not in text
        assert "t-leaked" not in text
        assert "«redacted»" in text
        assert "GDPC1" in text

    def test_call_envelope_omitted_when_no_params_passed(self):
        from parsimony.errors import EmptyDataError

        exc = EmptyDataError(provider="fred", message="no rows")
        content = translate_error(exc, "fred_fetch")
        text = content[0].text
        assert "call:" not in text
        assert text == "[fred_fetch] no rows"
