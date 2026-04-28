# Configuration

## Environment variables

| Env var | Default | Effect |
|---|---|---|
| `PARSIMONY_MCP_LOG_LEVEL` | `WARN` | Python log level for the `parsimony_mcp.*` logger family. Set `INFO` for startup connector count + discovery timing; `DEBUG` for per-call traces. All logs go to stderr. |
| `PARSIMONY_MCP_PROJECT_DIR` | (unset) | Pin the directory the bounded `.env` walk starts from. Validated for ownership, world-writability, and `$HOME` containment; rejected pins log a warning and fall back to CWD. |
| `<PLUGIN>_API_KEY` et al. | — | Each connector plugin has its own credential env vars. See the plugin's README, or open the `init`-generated `.env` for the list of keys you need. |
| `PARSIMONY_PROVIDERS_ALLOWLIST` | (unset) | Comma-separated list of plugin names to load. Handled by the kernel's discovery layer. See `parsimony-core` docs. |

## Secret-loading order

The server reads secrets in this order (highest priority first):

1. Programmatic overrides passed to `create_server` / `load_env`.
2. Pre-existing `os.environ` (the host's `mcpServers.*.env` block).
3. `.env` file values (loaded with `override=False`).

## `.env` discovery

The `.env` walk stops at the first directory containing `.git`,
`pyproject.toml`, or `.mcp.json`, refuses world-writable directories,
and never ascends past `$HOME`. Ownership and containment checks are
enforced by `parsimony_mcp._env`.

## CLI surface

The server itself takes no CLI flags. Console scripts:

- `parsimony-mcp` — start the stdio server (default).
- `parsimony-mcp init` — stamp `.mcp.json` + `.env` + `AGENTS.md` based on installed plugins.

## Security posture

- Every installed `parsimony-*` package gets imported by the server and
  the `init` scaffolder. Only install plugins you trust.
- To allowlist plugins explicitly, set `PARSIMONY_PROVIDERS_ALLOWLIST`
  (handled by the kernel's discovery layer).
- `.env` is written with `O_EXCL|O_NOFOLLOW` at mode `0o600` to defeat
  TOCTOU and symlink attacks.
- Logs never include exception messages — only `exc_type` and `tool` —
  because wrapped `httpx` errors embed bearer tokens through
  `__cause__`/`__context__`.
