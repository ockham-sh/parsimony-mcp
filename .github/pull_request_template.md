<!-- Thanks for contributing to parsimony-mcp. See CONTRIBUTING.md for the full checklist. -->

## What this PR changes

<!-- Short, specific. "Fix retry_after leak in RateLimitError message" — not "improvements". -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / maintenance
- [ ] Documentation
- [ ] Test-only change

## Behavior-shaping prose

- [ ] This PR **does not** change error directives, the instruction template, or the truncation footer. (If it does: check the box below.)
- [ ] If it does, an LLM eval pass was run and the results are linked in this PR.

## PR checklist

- [ ] `make check` passes locally (ruff + mypy strict + pytest)
- [ ] Tests added for new behavior
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] No exception messages emitted to logs (only `exc_type` + `tool`)
- [ ] No secrets or keys committed
