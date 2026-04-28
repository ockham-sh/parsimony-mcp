# parsimony-mcp

MCP (Model Context Protocol) stdio server adapter for
[parsimony](https://parsimony.dev). Exposes any installed
`parsimony-*` connector as an MCP tool to Claude Desktop, Claude Code,
Cursor, Continue, or any other MCP-compatible agent runtime.

## What this server does

`parsimony-mcp` is a **discovery** layer. It surfaces every connector
tagged `tool` (typically search, list, and metadata endpoints) to an
agent via MCP. For **bulk data retrieval** — full time series, multi-year
history — the server's instruction template tells the agent to write
Python that calls `discover.load_all().bind_env()` and then invokes
`connectors["<name>"](...)` inside a separate code-execution tool (a
Jupyter kernel, a REPL, etc.).

The exact tool surface depends on which `parsimony-*` plugins are
installed in your venv. See
[`parsimony-connectors`](https://github.com/ockham-sh/parsimony-connectors)
for the authoritative list.

## Quick links

- [Installation](installation.md) — `pip install` and client configuration
- [Configuration](configuration.md) — env vars and secret-loading order
- [Troubleshooting](troubleshooting.md) — common failure modes
- [API Reference](api-reference.md) — `create_server`, `connector_to_tool`, `result_to_content`
- [Programmatic Use](programmatic-use.md) — embedding the server in your own stack

## Repo boundaries

`parsimony-mcp` is a **consumer** of the kernel's `parsimony.providers`
entry-point contract. It is not itself a `parsimony.providers` plugin.

| Repo | PyPI | Role |
|---|---|---|
| [`parsimony`](https://github.com/ockham-sh/parsimony) | `parsimony-core` | The kernel — primitives, discovery, catalog |
| [`parsimony-connectors`](https://github.com/ockham-sh/parsimony-connectors) | `parsimony-<name>` | First-party data source plugins |
| [`parsimony-mcp`](https://github.com/ockham-sh/parsimony-mcp) | `parsimony-mcp` | This server |
