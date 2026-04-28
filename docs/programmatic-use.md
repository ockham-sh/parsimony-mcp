# Programmatic Use

## Embedding `create_server`

```python
from parsimony import discover
from parsimony_mcp import create_server

connectors = discover.load_all().bind_env().filter(tags=["tool"])
server = create_server(connectors)
# `server` is an mcp.server.lowlevel.Server — attach any transport.
```

`discover.load_all()` imports every installed `parsimony.providers`
entry point and merges their `CONNECTORS` exports. `.bind_env()` binds
each connector's declared env vars against `os.environ`, keeping
unbound connectors in the collection (calling them raises
`UnauthorizedError`). Use `connectors.unbound` to enumerate missing
credentials for a boot-time warning.

## Filtering connectors

```python
connectors = (
    discover.load_all()
    .bind_env()
    .filter(tags=["tool"])        # discovery endpoints only
    .filter(lambda c: c.name.startswith("fred_"))  # one provider
)
```

`.filter()` accepts either a `tags=[...]` keyword or a predicate
`(Connector) -> bool`.

## Bypassing `create_server`

If you want tool-by-tool control:

```python
from parsimony import discover
from parsimony_mcp import connector_to_tool, result_to_content

connectors = discover.load_all().bind_env()
tools = [connector_to_tool(c) for c in connectors if "tool" in c.tags]

# later, when MCP's call_tool arrives:
result = await connectors[name](**arguments)
content = result_to_content(result)
```

The bridge helpers are pure functions — you keep full control of error
translation, timeout policy, and transport.

## Custom error translation

The default 5-branch typed-error dispatch (`UnauthorizedError`,
`PaymentRequiredError`, `RateLimitError`, `EmptyDataError`,
`ConnectorError`) plus `ValidationError` plus catch-all lives in
`parsimony_mcp.bridge.translate_error`. It is not a public symbol but
you can call it from your own dispatch layer if needed:

```python
from parsimony_mcp.bridge import translate_error

try:
    result = await connectors[name](**arguments)
    content = result_to_content(result)
    is_error = False
except Exception as exc:
    content = translate_error(exc, tool_name=name)
    is_error = True
```

## Logging

```python
import logging
logging.getLogger("parsimony_mcp").setLevel(logging.INFO)
```

Stdout is reserved for MCP JSON-RPC framing; logs go to stderr via
`parsimony_mcp._logging`. Exception messages are never logged — only
`exc_type` and `tool`. This is load-bearing: wrapped `httpx` errors
embed bearer tokens through `__cause__`/`__context__`.
