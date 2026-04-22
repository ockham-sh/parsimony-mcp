# parsimony-mcp

> MCP (Model Context Protocol) stdio server adapter for [parsimony](https://parsimony.dev) — exposes any installed `parsimony-*` connector as an MCP tool to Claude Desktop, Claude Code, Cursor, Continue, or any other MCP-compatible agent runtime.

**Alpha — `0.2.0a1`.** Standalone release: the package was briefly colocated in the `parsimony-connectors` monorepo during the kernel discovery refactor and is now back in its own repo. Public API surface (`create_server`, `connector_to_tool`, `result_to_content`) is stable; behavior-shaping prose strings (error directives, instruction template, truncation footer) are guarded by the test suite and changes require an LLM eval pass.

---

## Quickstart

```bash
pip install parsimony-mcp parsimony-fred       # install + at least one connector
parsimony-mcp init                              # stamp .mcp.json + .env + AGENTS.md
$EDITOR .env                                    # fill in FRED_API_KEY=...
# restart Claude Desktop / Claude Code so it picks up .mcp.json
```

That's it. Ask your agent "list parsimony tools" to verify.

The `init` command introspects whichever `parsimony-*` plugins you've installed, refuses to overwrite existing files unless you pass `--force`, and refuses to write `.env` unless `.gitignore` already ignores it (leaked `.env` is the highest-impact failure mode for a local-secrets tool).

For a project that already has an `.mcp.json` you want to extend manually:

```bash
parsimony-mcp init --print                      # write the bundle to stdout
parsimony-mcp init --dry-run                    # show what would be written, touch nothing
parsimony-mcp init --force                      # overwrite existing files
```

For Claude Desktop's global config (no `.mcp.json` in projects), wire the server in by hand at `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "parsimony": {
      "command": "/absolute/path/to/your/venv/bin/parsimony-mcp",
      "env": { "FRED_API_KEY": "your-fred-key-here" }
    }
  }
}
```

Run `which parsimony-mcp` to get the absolute path.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Agent shows 0 parsimony tools | No `parsimony-*` plugins installed in the venv | `pip install parsimony-fred` (or any other plugin); restart the agent client. |
| Server log shows `loaded 0 connectors` | Same as above | As above. |
| Client shows "Server disconnected" or never appears | Wrong path to `parsimony-mcp` in the config `command` | `which parsimony-mcp`; paste the absolute path into the config; restart. |
| `parsimony-mcp init` says "target file(s) already exist" | `.mcp.json`/`.env`/`AGENTS.md` is already present | Re-run with `--force` to overwrite, or `--print` to write the bundle to stdout for manual merge, or delete the file(s) and re-run. |
| `parsimony-mcp init` says ".env is not gitignored" | Project has no `.gitignore`, or it doesn't ignore `.env` | Add `.env` to `.gitignore` (or create one); re-run. |
| Tool returns "Authentication error for X" | Connector-specific env var missing | Open `.env` and fill in the key for connector X (the comment header in `.env` links to the signup page). |
| Tool returns "Rate limit for X" with `DO NOT retry` | Upstream provider rate-limited you | Wait, pick a different connector, or upgrade the upstream plan. The agent will not retry. |
| Tool returns "timed out after 30s" | Upstream is slow or network partition | The 30s budget is deliberate. Retry manually if upstream recovers. |
| Tool returns `HTTPStatusError` after editing `.mcp.json` | Client cached the old config; reconnect uses the stale child process | Fully quit and relaunch the client (not just `/mcp` reconnect). |
| `${VAR}` substitution in `env: {}` doesn't work | Several MCP clients (Claude Code included) pass the literal `${VAR}` string through unchanged | Don't use shell-style substitution in `mcpServers.*.env`. Either hardcode the value or load via `.env` (the default `init` template uses `uv run --env-file .env`). |
| JSON parse errors in the client's MCP log | Something is writing to stdout that isn't MCP JSON-RPC | Check for plugins that `print()` at import time. Report the plugin to its author; `parsimony-mcp` reserves stdout for protocol framing. |

---

## Configuration

| Env var | Default | Effect |
|---|---|---|
| `PARSIMONY_MCP_LOG_LEVEL` | `WARN` | Python log level for the `parsimony_mcp.*` logger family. Set `INFO` for startup connector count + discovery timing; `DEBUG` for per-call traces. All logs go to stderr. |
| `PARSIMONY_MCP_PROJECT_DIR` | (unset) | Pin the directory the bounded `.env` walk starts from. Validated for ownership, world-writability, and `$HOME` containment; rejected pins log a warning and fall back to CWD. |
| `<PLUGIN>_API_KEY` et al. | — | Each connector plugin has its own credential env vars. See the plugin's README, or open the `init`-generated `.env` for the list of keys you need. |

The server reads secrets in this order (highest priority first):

1. Programmatic overrides passed to `create_server` / `load_env`.
2. Pre-existing `os.environ` (the host's `mcpServers.*.env` block).
3. `.env` file values (loaded with `override=False`).

The `.env` walk stops at the first directory containing `.git`, `pyproject.toml`, or `.mcp.json`, refuses world-writable directories, and never ascends past `$HOME`.

The server itself takes no CLI flags. Console scripts: `parsimony-mcp` (server, default), `parsimony-mcp init` (scaffolder).

---

## What this server exposes

`parsimony-mcp` is a **discovery** layer. It surfaces connectors whose authors tagged them `tool` — typically search, list, and metadata endpoints. For **bulk data retrieval** (full time series, multi-year history), the MCP instructions tell the agent to write Python that calls `discover.load_all().bind_env()` and then invokes `connectors["<name>"](...)`, and execute it in a separate code-execution tool (a Jupyter kernel, a REPL, etc.).

The exact tool surface depends on which `parsimony-*` plugins are installed in your venv. See the [parsimony-connectors monorepo](https://github.com/ockham-sh/parsimony-connectors) for the authoritative list.

**Security note.** Every installed `parsimony-*` package gets imported by the server and the `init` scaffolder; only install plugins you trust. To allowlist plugins explicitly, set `PARSIMONY_PROVIDERS_ALLOWLIST` (handled by the kernel's discovery layer; see `parsimony-core` docs).

---

## Programmatic use

```python
from parsimony import discover
from parsimony_mcp import create_server

connectors = discover.load_all().bind_env().filter(tags=["tool"])
server = create_server(connectors)
# `server` is an mcp.server.lowlevel.Server — attach any transport.
```

`discover.load_all()` loads every installed `parsimony.providers` entry point and merges them; `.bind_env()` binds each connector's declared env vars against `os.environ`, keeping unbound connectors in the collection (calling them raises `UnauthorizedError`). Use `connectors.unbound` to enumerate missing credentials for a boot-time warning.

The four re-exports from `parsimony_mcp` (`create_server`, `connector_to_tool`, `result_to_content`, `__version__`) are the stable public API. The `_env.py` and `init.py` modules are CLI internals and may evolve.

---

## Development

```bash
git clone https://github.com/ockham-sh/parsimony-mcp
cd parsimony-mcp
uv venv
uv pip install -e ".[dev]"
uv run pytest                                  # ~130 tests, ~1s
uv run ruff check parsimony_mcp tests
uv run mypy parsimony_mcp
```

`parsimony-core` is a dependency; during development you'll typically install it editable alongside:

```bash
uv pip install -e ../parsimony -e ".[dev]"
```

---

## License

Apache-2.0 — see [LICENSE](LICENSE).
