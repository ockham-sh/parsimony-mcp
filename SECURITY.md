# Security Policy

## Supported Versions

| Package | Version | Supported |
|---------|---------|-----------|
| parsimony-mcp | 0.2.x | Yes |

## Reporting a Vulnerability

**Please do not open public GitHub issues for security vulnerabilities.**

Email **security@ockham.sh** with:

- A description of the vulnerability
- Steps to reproduce (if applicable)
- The affected version(s)
- Any potential impact you've identified

Alternatively, open a private advisory via the GitHub "Report a
vulnerability" button on this repository.

### What to expect

- **48 hours**: We will acknowledge your report
- **7 days**: We will provide an initial assessment and estimated timeline
- **30 days**: We aim to release a fix for confirmed vulnerabilities

We will coordinate with you on disclosure timing. We follow responsible
disclosure practices and will credit reporters in release notes (unless
you prefer to remain anonymous).

## Scope

This policy covers the `parsimony-mcp` open-source package.

`parsimony-mcp` imports every installed `parsimony-*` provider at startup
(and from the `init` scaffolder). Vulnerabilities that originate in a
plugin or in the kernel's plugin-discovery path can be reported here and
we will route them — cross-reference the
[`parsimony` SECURITY.md](https://github.com/ockham-sh/parsimony/blob/main/SECURITY.md)
and the relevant plugin's advisory channel in your report.

## Supply-chain posture

- PyPI releases are published via
  [OIDC trusted publishing](https://docs.pypi.org/trusted-publishers/) —
  no long-lived `PYPI_API_TOKEN` secret exists in this repository.
- Third-party GitHub Actions are pinned by tag; `pip-audit --strict` is
  a required gate in CI.
- Server logs never include exception messages or tracebacks — only the
  exception class and tool name — because wrapped `httpx` errors
  routinely carry bearer tokens via `__cause__`/`__context__`.
- `init` refuses to write `.env` unless `.gitignore` already excludes it,
  and uses `O_EXCL|O_NOFOLLOW` at mode `0o600` to defeat TOCTOU /
  symlink attacks.
