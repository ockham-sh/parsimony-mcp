# Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Agent shows 0 parsimony tools | No `parsimony-*` plugins installed in the venv | `pip install parsimony-fred` (or any other plugin); restart the agent client. |
| Server log shows `loaded 0 connectors` | Same as above | As above. |
| Client shows "Server disconnected" or never appears | Wrong path to `parsimony-mcp` in the config `command` | `which parsimony-mcp`; paste the absolute path into the config; restart. |
| `parsimony-mcp init` says "target file(s) already exist" | `.mcp.json`/`.env`/`AGENTS.md` is already present | Re-run with `--force` to overwrite, or `--print` to write to stdout for manual merge, or delete the file(s) and re-run. |
| `parsimony-mcp init` says ".env is not gitignored" | Project has no `.gitignore`, or it doesn't ignore `.env` | Add `.env` to `.gitignore` (or create one); re-run. |
| Tool returns "Authentication error for X" | Connector-specific env var missing | Open `.env` and fill in the key for connector X (the comment header in `.env` links to the signup page). |
| Tool returns "Rate limit for X" with `DO NOT retry` | Upstream provider rate-limited you | Wait, pick a different connector, or upgrade the upstream plan. The agent will not retry. |
| Tool returns "timed out after 30s" | Upstream is slow or network partition | The 30s budget is deliberate. Retry manually if upstream recovers. |
| Tool returns `HTTPStatusError` after editing `.mcp.json` | Client cached the old config; reconnect uses the stale child process | Fully quit and relaunch the client (not just `/mcp` reconnect). |
| `${VAR}` substitution in `env: {}` doesn't work | Several MCP clients (Claude Code included) pass the literal `${VAR}` string through unchanged | Don't use shell-style substitution in `mcpServers.*.env`. Either hardcode the value or load via `.env` (the default `init` template uses `uv run --env-file .env`). |
| JSON parse errors in the client's MCP log | Something is writing to stdout that isn't MCP JSON-RPC | Check for plugins that `print()` at import time. Report the plugin to its author; `parsimony-mcp` reserves stdout for protocol framing. |

## Debug mode

Set `PARSIMONY_MCP_LOG_LEVEL=DEBUG` in the client's `mcpServers.*.env`
block. All logs go to stderr; Claude Desktop surfaces them in its MCP
log panel.

Startup logs at `INFO` show:

- Discovery timing (warning if >2000ms)
- Connector count (warning if 0)
- Unbound-connector warnings naming the missing env vars
