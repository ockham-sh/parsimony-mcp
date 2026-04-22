"""Unit tests for _logging.py — JSON stderr formatter + configure_logging."""

from __future__ import annotations

import json
import logging

import parsimony_mcp._logging as _logging_mod
from parsimony_mcp._logging import _JsonFormatter, configure_logging


class TestJsonFormatter:
    def test_emits_required_fields(self):
        formatter = _JsonFormatter()
        record = logging.LogRecord(
            name="parsimony_mcp.test", level=logging.INFO, pathname="x.py",
            lineno=1, msg="hello", args=(), exc_info=None,
        )
        payload = json.loads(formatter.format(record))
        assert payload["level"] == "INFO"
        assert payload["logger"] == "parsimony_mcp.test"
        assert payload["event"] == "hello"
        assert "ts" in payload

    def test_extras_merged(self):
        formatter = _JsonFormatter()
        record = logging.LogRecord(
            name="x", level=logging.WARNING, pathname="x.py",
            lineno=1, msg="event", args=(), exc_info=None,
        )
        record.tool = "fred"  # extras land as attrs
        record.duration_ms = 42
        payload = json.loads(formatter.format(record))
        assert payload["tool"] == "fred"
        assert payload["duration_ms"] == 42

    def test_exception_class_only_no_traceback(self):
        """Critical: full tracebacks embed tokens via __cause__/__context__."""
        formatter = _JsonFormatter()
        try:
            raise ValueError("secret inside")
        except ValueError:
            import sys
            record = logging.LogRecord(
                name="x", level=logging.ERROR, pathname="x.py",
                lineno=1, msg="failed", args=(), exc_info=sys.exc_info(),
            )
        payload = json.loads(formatter.format(record))
        assert payload["exc_type"] == "ValueError"
        # Full serialized output must not embed the exception message
        assert "secret inside" not in formatter.format(record)


class TestConfigureLogging:
    def test_idempotent(self, monkeypatch):
        monkeypatch.setattr(_logging_mod, "_configured", False)
        logger = logging.getLogger("parsimony_mcp")
        # snapshot handler count before
        before = len(logger.handlers)
        configure_logging()
        after_first = len(logger.handlers)
        configure_logging()  # idempotent
        after_second = len(logger.handlers)
        assert after_first == before + 1
        assert after_second == after_first
