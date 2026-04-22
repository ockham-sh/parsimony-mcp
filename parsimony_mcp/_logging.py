"""Stderr JSON logging for parsimony-mcp.

stdout is owned by the MCP SDK's JSON-RPC framing; logging to stdout corrupts
the wire protocol. Every log line goes to stderr, which Claude Desktop and
similar runtimes capture into their MCP log pane.

The formatter is intentionally ~30 lines with no external dependencies — the
alpha doesn't need structlog or python-json-logger, and pulling either in
adds surface area for no benefit.

Honors ``PARSIMONY_MCP_LOG_LEVEL`` (default ``WARN``) so steady-state
operation is quiet. Set ``DEBUG`` for diagnosis.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

_RESERVED = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
        "message",
    }
)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        if record.exc_info:
            # Log only the exception class name — never the full chain, which
            # commonly embeds bearer tokens via __cause__ / __context__ on
            # wrapped httpx errors. Operators who need full tracebacks set
            # PARSIMONY_MCP_LOG_LEVEL=DEBUG and accept the risk.
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else "Unknown"
        extras = {k: v for k, v in record.__dict__.items() if k not in _RESERVED and not k.startswith("_")}
        if extras:
            payload.update(extras)
        return json.dumps(payload, default=str, separators=(",", ":"))


_configured = False


def configure_logging() -> None:
    """Install the JSON formatter on the root parsimony_mcp logger.

    Idempotent — safe to call multiple times. The console-script entry point
    calls this before any library code emits a log record.
    """
    global _configured
    if _configured:
        return
    level = os.environ.get("PARSIMONY_MCP_LOG_LEVEL", "WARN").upper()
    logger = logging.getLogger("parsimony_mcp")
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)
    # Don't propagate to root — the MCP SDK may install its own handlers.
    logger.propagate = False
    _configured = True
