"""Filter which connectors are exposed as MCP tools.

Three filter styles:
1. Tag-based — only connectors tagged `tool` (the `init`-default).
2. Predicate — arbitrary `(Connector) -> bool`.
3. Explicit allowlist — drive from `PARSIMONY_PROVIDERS_ALLOWLIST`.

Usage:

    python examples/custom_filter.py
"""
from __future__ import annotations

import os

from parsimony import discover

from parsimony_mcp import create_server


def build_server():
    connectors = discover.load_all().bind_env()

    # 1. Keep tool-tagged connectors only (what the default server does).
    connectors = connectors.filter(tags=["tool"])

    # 2. Drop connectors whose name doesn't start with one of these prefixes.
    allowed_prefixes = ("fred_", "sdmx_", "treasury_")
    connectors = connectors.filter(lambda c: c.name.startswith(allowed_prefixes))

    # 3. Honour PARSIMONY_PROVIDERS_ALLOWLIST explicitly if set.
    allow = os.environ.get("PARSIMONY_PROVIDERS_ALLOWLIST", "")
    if allow:
        allowed = {p.strip() for p in allow.split(",") if p.strip()}
        connectors = connectors.filter(lambda c: c.provider in allowed)

    return create_server(connectors)


if __name__ == "__main__":
    server = build_server()
    # Attach any transport — see programmatic_server.py for a stdio example.
    print(f"Server ready with {len(server.tools) if hasattr(server, 'tools') else '?'} tools.")
