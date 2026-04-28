# API Reference

The stable public API is the four symbols re-exported from
`parsimony_mcp`:

- `create_server`
- `connector_to_tool`
- `result_to_content`
- `__version__`

The `_env.py` and `init.py` modules are CLI internals and may evolve.

## `create_server(connectors) -> mcp.server.lowlevel.Server`

Wires a `parsimony.Connectors` collection into an `mcp.server.lowlevel.Server`.
Every tool-tagged connector becomes an MCP tool; every other connector
is skipped.

```python
from parsimony import discover
from parsimony_mcp import create_server

connectors = discover.load_all().bind_env().filter(tags=["tool"])
server = create_server(connectors)
# `server` is an mcp.server.lowlevel.Server — attach any transport.
```

### Behavior

- Every error response carries `isError=True`.
- `RateLimitError` / `PaymentRequiredError` error text includes a
  "DO NOT retry" directive so agents don't tight-loop.
- Each connector invocation is wrapped in `asyncio.timeout(30)`.
- The instruction template contains a delimited `<catalog>…</catalog>`
  block, guarding against plugin-author docstrings that could override
  host prose.

## `connector_to_tool(conn) -> mcp.types.Tool`

Pure function. Converts a single `parsimony.Connector` into an
`mcp.types.Tool` definition. Useful when you want to embed MCP tool
handling in a server you already have.

## `result_to_content(result) -> list[mcp.types.Content]`

Pure function. Converts a `parsimony.Result` into MCP `Content`
objects — a tabular preview via [TOON](https://github.com/cloudflare/toon)
encoding for `DataFrame` results, plus a self-describing truncation
directive:

> `(showing N of M rows — this is a discovery preview; for the full dataset call parsimony.client['<connector>'](...) in Python)`

DataFrame cells are sanitized: `|` and backticks are escaped, newlines
become spaces, per-cell length is capped at 500 characters.

## `__version__: str`

Derived from `importlib.metadata.version("parsimony-mcp")`. The installed
wheel's version is the single source of truth.
