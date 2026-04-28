# parsimony-mcp

## Commands

```bash
make check      # lint + typecheck + test
make test       # pytest
make test-cov   # pytest with coverage report
make lint       # ruff check
make typecheck  # mypy strict
make format     # ruff format + auto-fix
```

Raw commands:

```bash
uv run pytest                              # ~130 tests, ~1s
uv run ruff check parsimony_mcp tests
uv run mypy parsimony_mcp
uv run pip-audit --strict
```

## Key files

| What | Where |
|------|-------|
| Public surface | `parsimony_mcp/__init__.py` |
| Stdio entry point + startup observability | `parsimony_mcp/__main__.py` |
| `create_server` builder + `_MCP_SERVER_INSTRUCTIONS` template | `parsimony_mcp/server.py` |
| `connector_to_tool`, `result_to_content`, `translate_error` | `parsimony_mcp/bridge.py` |
| Bounded `.env` loader, `$HOME`-containment + ownership checks | `parsimony_mcp/_env.py` |
| `init` scaffolder (`.mcp.json` + `.env` + `AGENTS.md`) | `parsimony_mcp/init.py` |
| Stderr JSON structured logging | `parsimony_mcp/_logging.py` |
| Agent-contract guard tests | `tests/test_agent_contract.py`, `tests/test_bridge.py` |

## Rules

- Python 3.11+; `mypy --strict`; ruff with `S` (flake8-bandit) enabled; 120-char lines.
- **Stdout is reserved for MCP JSON-RPC.** Logging, errors, telemetry → stderr.
- **Never emit raw exception messages to logs** — only `exc_type` and `tool`. Wrapped `httpx` errors commonly embed bearer tokens through `__cause__`/`__context__`.
- Every error response sets `isError=True`. `RateLimitError` / `PaymentRequiredError` messages include "DO NOT retry" directives so agents don't tight-loop.
- Per-call `asyncio.timeout(30s)` on every connector invocation.
- The public API (`create_server`, `connector_to_tool`, `result_to_content`, `__version__`) is stable; `_env.py` / `init.py` are CLI internals.
- Behavior-shaping prose strings (error directives, instruction template, truncation footer) are guarded by tests. Changes require an LLM eval pass alongside unit tests.
- `init` refuses to write `.env` unless `.gitignore` already ignores it; writes with `O_EXCL|O_NOFOLLOW` at mode `0o600`.
- This repo is a **consumer** of `parsimony.providers`, not a plugin. New data connectors go to [`parsimony-connectors`](https://github.com/ockham-sh/parsimony-connectors).
- Run `make check` before any commit.
