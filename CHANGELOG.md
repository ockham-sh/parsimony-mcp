# Changelog

All notable changes to `parsimony-mcp` will be documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.2.0]

`parsimony-mcp` is back in its own repository after a brief stop in the `parsimony-connectors` monorepo during the kernel's discovery refactor. The kernel shipped `parsimony-core==0.4` with the new `parsimony.discover` surface (`iter_providers`, `load`, `load_all`) and a richer `Connectors` verb set (`merge`, `bind_env`, `env_vars`, `unbound`, `replace`); `parsimony.discovery` and `parsimony.client` are gone. This release rewires `parsimony-mcp` to the new surface and picks up the improved `init` subcommand, `_env.py` bounded `.env` loader, and `.gitignore`-guarded scaffolder from the monorepo era.

### Added

- `parsimony-mcp init` subcommand (from the monorepo era) — stamps `.mcp.json` and `.env` templates based on whichever `parsimony-*` plugins are installed. Refuses to write `.env` unless `.gitignore` already ignores it; writes `.env` with `O_EXCL|O_NOFOLLOW` at mode `0o600` to defeat TOCTOU and symlink attacks.
- `parsimony_mcp._env.load_env(cwd, ...)` — bounded upward walk for `.env` discovery. Stops at project anchors (`.git`, `pyproject.toml`, `.mcp.json`), never ascends past `$HOME`, refuses world-writable directories. Honors `PARSIMONY_MCP_PROJECT_DIR` only if the pin passes ownership + containment checks.
- `parsimony_mcp._env.load_dotenv` — re-export of `python-dotenv`'s `load_dotenv`. The kernel used to own `parsimony.load_dotenv`; ownership moved here as part of the 0.4 kernel split.
- Boot-time unbound warning: after `discover.load_all().bind_env()`, each connector with unresolved required env vars logs a WARNING naming the missing env vars. Replaces the old "silently drop unconfigured plugins" behaviour — unbound connectors stay in the tool catalog and raise `UnauthorizedError` on call.
- TOON (Token-Oriented Object Notation) encoding for `result_to_content` table previews via the `toon-format` library — saves 30-50% of agent tokens versus the previous markdown table encoder, and does not need markdown-pipe escaping.

### Changed

- **BREAKING:** `parsimony-core` pin bumped from `>=0.1.0a1,<0.3` to `>=0.4,<0.5`. The kernel's discovery surface changed API: plugins no longer export `ENV_VARS` / `PROVIDER_METADATA` / `__version__`; env-var mapping is declared via `@connector(env={"api_key": "FRED_API_KEY"})` and surfaces through `Connector.env_map`.
- `__main__.py` now calls `discover.load_all().bind_env()` (kernel 0.4 surface) instead of `build_connectors_from_env()` (kernel 0.1-0.3). Same 2-second slow-discovery warning threshold, same stderr JSON logging, same 30s per-call timeout.
- `init.py` plugin introspection now reads the kernel `Provider.homepage` (from PEP 621 `[project.urls]`) and `Connectors.env_vars()` (aggregated from every `@connector(env=...)` declaration). Plugins that fail to load are surfaced under "Skipped" without aborting the wizard.
- `python-dotenv` moves from a kernel transitive dep to a direct dep of `parsimony-mcp`: we are now the sole consumer.

### Removed

- `parsimony.discovery.build_connectors_from_env` import — deleted in kernel 0.4, replaced by `parsimony.discover.load_all`.
- `parsimony.client` references in agent-facing instructions and the truncation directive — rewritten to the new escape hatch (`discover.load_all().bind_env()` then `connectors["<name>"](...)`). The deleted `parsimony.client` lazy-singleton no longer exists in kernel 0.4. Behavior-shaping prose tests in `tests/test_agent_contract.py` and `tests/test_bridge.py` were updated in lockstep.

### Python support

- CPython 3.11, 3.12, 3.13.

[0.2.0a1]: https://github.com/ockham-sh/parsimony-mcp/releases/tag/v0.2.0a1

## [0.1.0a1] — Unreleased

First standalone release. `parsimony-mcp` was previously shipped inside the `parsimony-core` kernel at `parsimony.mcp`; the kernel rewrite extracted it into this package.

### Added

- `create_server(connectors)` builder that wires a `parsimony.Connectors` collection into an `mcp.server.lowlevel.Server`, ready to be attached to any MCP transport. Stdio transport is provided by the `parsimony-mcp` console script (alias for `python -m parsimony_mcp`).
- `connector_to_tool(conn)` and `result_to_content(result)` as re-exported pure helpers for callers embedding MCP handlers in their own server.
- Per-call `asyncio.timeout(30s)` on connector invocations. Timeouts surface as a deterministic error observation with `isError=True`.
- 5-branch typed-error handling (`UnauthorizedError`, `PaymentRequiredError`, `RateLimitError` with `quota_exhausted`/`retry_after`, `EmptyDataError`, generic `ConnectorError`) plus Pydantic `ValidationError`, kernel `TypeError("Missing params")`, unknown-tool, and catch-all. Every error response carries the MCP-protocol `isError=True` flag and a behavioral directive in the text (`DO NOT retry` where appropriate) so agents don't tight-loop.
- DataFrame cell sanitization in `result_to_content` — escapes `|` and backticks, replaces newlines with spaces, caps per-cell length at 500 chars. A compromised upstream provider cannot forge markdown rows or inject system-prompt-shaped strings into agent observations.
- Self-describing truncation directive: `(showing N of M rows — this is a discovery preview; for the full dataset call parsimony.client['<connector>'](...) in Python)`.
- Instruction template with a clearly delimited `<catalog>...</catalog>` block so plugin-author-controlled connector docstrings cannot override host instructions.
- Stderr JSON structured logging (`parsimony_mcp._logging`). Honors `PARSIMONY_MCP_LOG_LEVEL` env var (default `WARN`). Never emits exception messages or tracebacks to logs — only `exc_type` and `tool` — because wrapped `httpx` errors commonly embed bearer tokens through `__cause__`/`__context__`.
- Startup observability in `__main__._run()`: discovery timing, connector count, warning if zero connectors, warning if discovery exceeds 2000ms.

### Changed

- `__init__.py` now eagerly exports `create_server`, `connector_to_tool`, `result_to_content`, and derives `__version__` from `importlib.metadata`. The obsolete lazy-import alias pointing at `parsimony.mcp.server` (which no longer exists in the kernel) has been removed.
- `__main__.py` exposes a synchronous `main()` wrapper around `asyncio.run(_run())` so `[project.scripts]` can reference it — console scripts cannot point at coroutines.
- The `call_tool` handler disables MCP SDK's default JSON Schema validation (`validate_input=False`) and handles all validation through `parsimony.connector.Connector.__call__`'s Pydantic layer, routed through `translate_error`. This keeps error formatting consistent and the redaction rules in one place.

### Security

- Connector exception messages are **never** spliced into tool responses. Each `ConnectorError` branch emits a fixed user-safe string naming only the exception class and `provider` attribute. Raw messages (which routinely embed `?api_key=...` query strings) are redacted before ever leaving this package.
- Pydantic `ValidationError` responses surface up to 5 `loc: msg` entries but never include `input_value`. If a user accidentally types an API key as a tool argument, it does not round-trip through the LLM transcript.

### Dependencies

- `parsimony-core >=0.1.0a1, <0.3`
- `mcp >=1.0, <2`
- `tabulate >=0.9.0, <1`
- `pandas >=2.0, <3`

### Python support

- CPython 3.11, 3.12, 3.13.

[0.1.0a1]: https://github.com/ockham-sh/parsimony-mcp/releases/tag/v0.1.0a1
