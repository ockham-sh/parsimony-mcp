# Contributing to parsimony-mcp

Thanks for your interest. This repo ships the MCP (Model Context
Protocol) stdio server adapter for parsimony. It is a **consumer** of
the kernel's `parsimony.providers` entry-point contract — it is not
itself a `parsimony.providers` plugin.

Where contributions go:

- **New or updated data connectors:**
  [`ockham-sh/parsimony-connectors`](https://github.com/ockham-sh/parsimony-connectors).
  This repo does not accept provider-specific code.
- **Kernel / discovery / connector contract changes:**
  [`ockham-sh/parsimony`](https://github.com/ockham-sh/parsimony).
- **MCP bridge, error translation, stdio transport, `init` scaffolder,
  `.env` loader:** here.

---

## Development setup

```bash
git clone https://github.com/ockham-sh/parsimony-mcp
cd parsimony-mcp
uv venv
uv pip install -e ".[dev]"
```

During kernel co-development you'll typically install the kernel editable
side-by-side:

```bash
uv pip install -e ../parsimony -e ".[dev]"
```

### Quick commands

```bash
make check      # lint + typecheck + test
make test       # pytest
make test-cov   # pytest with coverage report
make lint       # ruff check
make typecheck  # mypy
make format     # ruff format + auto-fix
```

Or run them directly:

```bash
uv run pytest                                 # ~130 tests, ~1s
uv run ruff check parsimony_mcp tests
uv run mypy parsimony_mcp
uv run pip-audit --strict
```

Run `make check` before submitting a PR. CI runs the same commands plus a
Python 3.11 / 3.12 / 3.13 matrix.

---

## Making changes

1. **Fork** this repository.
2. **Create a feature branch** from `main` (`git checkout -b feat/my-change`).
3. **Write tests first** (TDD). Behavior-shaping prose strings (error
   directives, instruction template, truncation footer) are guarded by
   tests in `tests/test_agent_contract.py` and `tests/test_bridge.py` —
   changes there require an LLM eval pass alongside unit-test updates.
4. **Run `make check`**.
5. **Update `CHANGELOG.md`** under `[Unreleased]`.
6. **Open a PR** with a clear description.

### Code style

- [ruff](https://docs.astral.sh/ruff/) with `S` (flake8-bandit) enabled —
  120-char lines.
- [mypy strict](https://mypy.readthedocs.io/en/stable/command_line.html#cmdoption-mypy-strict).
- Type hints on all function signatures (tests are exempted).
- Never log exception messages — only `exc_type` and `tool`. Wrapped
  `httpx` errors embed bearer tokens via `__cause__`/`__context__`.
- Stdout is reserved for MCP JSON-RPC framing. Logging goes to stderr
  via `parsimony_mcp._logging`.

### Key files

| What | Where |
|------|-------|
| Public surface | `parsimony_mcp/__init__.py` |
| Stdio entry point | `parsimony_mcp/__main__.py` |
| Server builder | `parsimony_mcp/server.py` |
| Connector → tool bridge, error translation | `parsimony_mcp/bridge.py` |
| `.env` loader | `parsimony_mcp/_env.py` |
| `init` scaffolder | `parsimony_mcp/init.py` |
| Structured stderr logging | `parsimony_mcp/_logging.py` |
| Tests | `tests/` |
| Agent-contract guard tests | `tests/test_agent_contract.py`, `tests/test_bridge.py` |

---

## Pull request guidelines

- One focused change per PR.
- Include tests for new behavior.
- Update `CHANGELOG.md` under `[Unreleased]`.
- Reference any related issues.
- Use conventional commit messages: `feat:`, `fix:`, `refactor:`,
  `docs:`, `test:`, `chore:`.

## Reporting bugs

For bugs, open a GitHub issue with the template. For security issues see
[`SECURITY.md`](SECURITY.md) — do **not** open a public issue.

## Code of conduct

See [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
