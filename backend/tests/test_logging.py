"""Unit tests for logging configuration."""

from __future__ import annotations

import json
import logging

from agent_platform.logging_config import JsonLogFormatter, configure_logging


def test_json_formatter_emits_valid_json_with_context() -> None:
    formatter = JsonLogFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1, msg="hello", args=(), exc_info=None
    )
    record.agent_id = "dev-123"  # caller-supplied context
    payload = json.loads(formatter.format(record))
    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["agent_id"] == "dev-123"


def test_json_formatter_includes_exception() -> None:
    formatter = JsonLogFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="t", level=logging.ERROR, pathname=__file__, lineno=1, msg="err", args=(), exc_info=sys.exc_info()
        )
    payload = json.loads(formatter.format(record))
    assert "boom" in payload["exception"]


def test_configure_logging_json_replaces_handlers() -> None:
    configure_logging("DEBUG", json_format=True)
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonLogFormatter)
    # Reset to a plain configuration so other tests are unaffected.
    configure_logging("INFO", json_format=False)
