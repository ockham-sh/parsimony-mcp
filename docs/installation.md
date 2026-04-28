# Installation

## Install from PyPI

```bash
pip install parsimony-mcp parsimony-fred       # install + at least one connector
```

At least one `parsimony-*` plugin must be installed; the server has no
connectors of its own. Browse the
[connector catalog](https://github.com/ockham-sh/parsimony-connectors)
to see what's available.

## Stamp the client config

```bash
parsimony-mcp init                              # stamp .mcp.json + .env + AGENTS.md
$EDITOR .env                                    # fill in FRED_API_KEY=...
```

The `init` command introspects whichever `parsimony-*` plugins you've
installed, refuses to overwrite existing files unless you pass
`--force`, and refuses to write `.env` unless `.gitignore` already
ignores it (leaked `.env` is the highest-impact failure mode for a
local-secrets tool).

For a project that already has an `.mcp.json` you want to extend
manually:

```bash
parsimony-mcp init --print                      # write bundle to stdout
parsimony-mcp init --dry-run                    # show what would be written, touch nothing
parsimony-mcp init --force                      # overwrite existing files
```

## Claude Desktop (global config)

For Claude Desktop's global config (no `.mcp.json` in projects), wire the
server in by hand at
`~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

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

## Verify

Restart Claude Desktop / Claude Code so it picks up the config, then ask
your agent: **"list parsimony tools"**. You should see tools named after
each `parsimony-*` connector tagged `tool`.

At the command line:

```bash
python -c "from parsimony import discover; print([p.name for p in discover.iter_providers()])"
```

should list every installed plugin.

## Python support

CPython 3.11, 3.12, 3.13.
