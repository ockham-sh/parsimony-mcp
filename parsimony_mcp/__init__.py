"""Parsimony MCP server adapter.

Exposes a parsimony :class:`Connectors` collection as MCP tools::

    from parsimony import discover
    from parsimony_mcp import create_server

    connectors = discover.load_all().bind_env().filter(tags=["tool"])
    server = create_server(connectors)
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from parsimony_mcp.bridge import connector_to_tool, result_to_content
from parsimony_mcp.server import create_server

try:
    __version__ = version("parsimony-mcp")
except PackageNotFoundError:  # pragma: no cover — only during in-tree development before install
    __version__ = "0.0.0+unknown"

__all__ = ["__version__", "connector_to_tool", "create_server", "result_to_content"]
