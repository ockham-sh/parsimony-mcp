"""Embed parsimony-mcp as a library.

Runs the MCP server over stdio, exposing every tool-tagged connector
from whichever `parsimony-*` plugins are installed in the venv.

Usage:

    python examples/programmatic_server.py
"""
from __future__ import annotations

import asyncio

from mcp.server.stdio import stdio_server
from parsimony import discover

from parsimony_mcp import create_server


async def main() -> None:
    connectors = discover.load_all().bind_env().filter(tags=["tool"])
    if not connectors:
        raise SystemExit(
            "No parsimony-* plugins found. Install at least one, e.g. "
            "`pip install parsimony-fred`."
        )

    server = create_server(connectors)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
