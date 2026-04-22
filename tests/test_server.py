"""Integration tests for the MCP server.

Drives the real :class:`mcp.server.lowlevel.Server` through its public
handler surface via the SDK's request-handler dispatch. Every call_tool
branch (happy path, unknown tool, validation, each of the 5 parsimony
errors, timeout, generic exception) is exercised end-to-end so that the
``isError`` flag, the ``_translate_error`` funnel, and the Pydantic
wiring all stay correct together.
"""

from __future__ import annotations

import asyncio
from typing import cast

import pandas as pd
from mcp import types as mcp_types
from mcp.server.lowlevel.server import Server
from parsimony.connector import Connectors, connector
from parsimony.errors import (
    ConnectorError,
    EmptyDataError,
    PaymentRequiredError,
    RateLimitError,
    UnauthorizedError,
)
from parsimony.result import Column, ColumnRole, OutputConfig
from pydantic import BaseModel, Field

from parsimony_mcp import create_server

SEARCH_OUTPUT = OutputConfig(
    columns=[
        Column(name="id", role=ColumnRole.KEY),
        Column(name="title", role=ColumnRole.TITLE),
    ],
)


class StubParams(BaseModel):
    query: str = Field(..., description="Search query")


class IntParams(BaseModel):
    n: int = Field(..., description="A number")


@connector(output=SEARCH_OUTPUT, tags=["tool"], name="int_tool")
async def int_tool(params: IntParams) -> pd.DataFrame:
    """A stub tool that wants an int."""
    return pd.DataFrame({"id": [str(params.n)], "title": ["r"]})


def _make_error_connector(name: str, exc: Exception):
    """Create a connector that always raises the given exception."""

    @connector(name=name, output=SEARCH_OUTPUT, tags=["tool"])
    async def _raises(params: StubParams) -> pd.DataFrame:
        """Raises an error for testing."""
        raise exc

    return _raises


@connector(output=SEARCH_OUTPUT, tags=["tool"])
async def ok_tool(params: StubParams) -> pd.DataFrame:
    """A stub tool that returns successfully."""
    return pd.DataFrame({"id": ["X"], "title": ["Result"]})


async def _call_tool(
    server: Server, name: str, arguments: dict
) -> mcp_types.CallToolResult:
    handler = server.request_handlers[mcp_types.CallToolRequest]
    request = mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(name=name, arguments=arguments),
    )
    result = await handler(request)
    narrowed = result.root if hasattr(result, "root") else result
    return cast(mcp_types.CallToolResult, narrowed)


async def _list_tools(server: Server) -> mcp_types.ListToolsResult:
    handler = server.request_handlers[mcp_types.ListToolsRequest]
    request = mcp_types.ListToolsRequest(method="tools/list")
    result = await handler(request)
    narrowed = result.root if hasattr(result, "root") else result
    return cast(mcp_types.ListToolsResult, narrowed)


def _text(result: mcp_types.CallToolResult) -> str:
    assert result.content, "Expected at least one content block"
    block = result.content[0]
    assert isinstance(block, mcp_types.TextContent)
    return block.text


class TestListTools:
    async def test_list_tools_single(self) -> None:
        server = create_server(Connectors([ok_tool]))
        result = await _list_tools(server)
        assert len(result.tools) == 1
        assert result.tools[0].name == "ok_tool"

    async def test_tool_count_matches_tool_tagged_subset(self, all_connectors) -> None:
        """``create_server`` accepts the FULL bundle but the MCP tool list
        is filtered to the ``"tool"``-tagged subset. mock_search + mock_profile
        are tagged 'tool'; mock_fetch is not."""
        server = create_server(all_connectors)
        result = await _list_tools(server)
        assert len(result.tools) == 2
        names = {t.name for t in result.tools}
        assert names == {"mock_search", "mock_profile"}


class TestInstructions:
    def test_instructions_contain_framing(self, all_connectors) -> None:
        server = create_server(all_connectors)
        assert server.instructions is not None
        assert "parsimony" in server.instructions.lower()
        assert "discover" in server.instructions.lower()
        assert "fetch" in server.instructions.lower()

    def test_instructions_contain_tool_tagged_in_discovery_block(
        self, all_connectors
    ) -> None:
        server = create_server(all_connectors)
        assert server.instructions is not None
        assert "MCP discovery tools" in server.instructions
        assert "mock_search" in server.instructions

    def test_instructions_contain_fetch_only_in_bulk_block(self, all_connectors) -> None:
        """Non-tool-tagged connectors MUST appear in the catalog under the
        bulk-fetch heading so the agent can route ``connectors[name]``
        calls without guessing names from the discovery surface alone."""
        server = create_server(all_connectors)
        assert server.instructions is not None
        assert "Bulk fetch connectors" in server.instructions
        # mock_fetch is NOT tagged 'tool' — it must appear here so the
        # agent knows to dispatch via connectors['mock_fetch'](...).
        assert "mock_fetch" in server.instructions

    def test_catalog_is_delimited(self, all_connectors) -> None:
        """Plugin-author prose must be clearly scoped as data, not instructions."""
        server = create_server(all_connectors)
        assert server.instructions is not None
        assert "<catalog>" in server.instructions
        assert "</catalog>" in server.instructions


class TestCallToolSuccess:
    async def test_successful_call_not_marked_error(self) -> None:
        server = create_server(Connectors([ok_tool]))
        result = await _call_tool(server, "ok_tool", {"query": "hello"})
        assert result.isError is False
        text = _text(result)
        assert "X" in text
        assert "Result" in text


class TestCallToolUnknownTool:
    async def test_unknown_tool_is_marked_error(self) -> None:
        server = create_server(Connectors([ok_tool]))
        result = await _call_tool(server, "nonexistent", {"query": "x"})
        assert result.isError is True
        assert "Unknown tool" in _text(result)


class TestCallToolValidationError:
    async def test_missing_required_arg_is_marked_error(self) -> None:
        """Kernel raises TypeError('Missing params') when no args at all."""
        server = create_server(Connectors([ok_tool]))
        result = await _call_tool(server, "ok_tool", {})
        assert result.isError is True
        text = _text(result)
        assert "Invalid parameters" in text

    async def test_wrong_type_triggers_validation_error(self) -> None:
        """Wrong-type args trigger Pydantic ValidationError, not TypeError."""
        server = create_server(Connectors([int_tool]))
        result = await _call_tool(server, "int_tool", {"n": "not-an-int"})
        assert result.isError is True
        text = _text(result)
        assert "Invalid parameters" in text
        # Field name must surface; raw input value must not.
        assert "n" in text
        assert "not-an-int" not in text


class TestCallToolUnauthorizedError:
    async def test_unauthorized(self) -> None:
        c = _make_error_connector("err_unauth", UnauthorizedError(provider="test_prov"))
        server = create_server(Connectors([c]))
        result = await _call_tool(server, "err_unauth", {"query": "x"})
        assert result.isError is True
        text = _text(result)
        assert "Authentication" in text
        assert "test_prov" in text
        assert "DO NOT retry" in text


class TestCallToolPaymentRequiredError:
    async def test_payment_required(self) -> None:
        c = _make_error_connector("err_pay", PaymentRequiredError(provider="premium"))
        server = create_server(Connectors([c]))
        result = await _call_tool(server, "err_pay", {"query": "x"})
        assert result.isError is True
        text = _text(result)
        assert "DO NOT retry" in text
        assert "premium" in text


class TestCallToolRateLimitError:
    async def test_burst_limit_gives_retry_after(self) -> None:
        c = _make_error_connector(
            "err_rl", RateLimitError(provider="fast", retry_after=30.0)
        )
        server = create_server(Connectors([c]))
        result = await _call_tool(server, "err_rl", {"query": "x"})
        assert result.isError is True
        text = _text(result)
        assert "30 seconds" in text
        assert "DO NOT retry" in text

    async def test_quota_exhausted_says_do_not_retry(self) -> None:
        c = _make_error_connector(
            "err_quota",
            RateLimitError(provider="quota", retry_after=0.0, quota_exhausted=True),
        )
        server = create_server(Connectors([c]))
        result = await _call_tool(server, "err_quota", {"query": "x"})
        assert result.isError is True
        assert "DO NOT retry" in _text(result)


class TestCallToolEmptyDataError:
    async def test_empty_data(self) -> None:
        c = _make_error_connector(
            "err_empty", EmptyDataError(provider="empty", message="No rows")
        )
        server = create_server(Connectors([c]))
        result = await _call_tool(server, "err_empty", {"query": "x"})
        assert result.isError is True
        text = _text(result)
        assert "No data" in text


class TestCallToolConnectorError:
    async def test_generic_connector_error_redacts_raw_message(self) -> None:
        """Raw ConnectorError messages may embed secrets via query strings."""
        raw = "GET https://api.example.com/v1/data?api_key=REAL_KEY failed"
        c = _make_error_connector("err_gen", ConnectorError(raw, provider="slow"))
        server = create_server(Connectors([c]))
        result = await _call_tool(server, "err_gen", {"query": "x"})
        assert result.isError is True
        text = _text(result)
        assert "slow" in text
        assert "REAL_KEY" not in text


class TestCallToolTimeout:
    async def test_slow_connector_is_marked_error_with_directive(self, monkeypatch) -> None:
        """A connector that hangs past the timeout budget must surface cleanly."""
        # Shorten the timeout so the test doesn't take 30s
        import parsimony_mcp.server as server_mod
        monkeypatch.setattr(server_mod, "_CALL_TIMEOUT_SECONDS", 0.1)

        @connector(name="slow_tool", output=SEARCH_OUTPUT, tags=["tool"])
        async def slow_tool(params: StubParams) -> pd.DataFrame:
            """A stub tool that hangs."""
            await asyncio.sleep(5)
            return pd.DataFrame()

        server = create_server(Connectors([slow_tool]))
        result = await _call_tool(server, "slow_tool", {"query": "x"})
        assert result.isError is True
        text = _text(result)
        assert "timed out" in text
        assert "DO NOT" in text


class TestCallToolUnexpectedException:
    async def test_unhandled_exception_does_not_leak_message(self) -> None:
        c = _make_error_connector(
            "err_boom", RuntimeError("sensitive internal state: token=abc123")
        )
        server = create_server(Connectors([c]))
        result = await _call_tool(server, "err_boom", {"query": "x"})
        assert result.isError is True
        text = _text(result)
        assert "Internal error" in text
        assert "abc123" not in text


class TestLazyImports:
    def test_package_exports_create_server(self) -> None:
        import parsimony_mcp

        assert callable(parsimony_mcp.create_server)

    def test_package_version(self) -> None:
        import parsimony_mcp

        assert isinstance(parsimony_mcp.__version__, str)
