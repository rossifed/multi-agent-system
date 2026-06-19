"""Logging configuration.

Provides structured logging with two formats:
- Human-readable (default, for local development).
- JSON (for production / log aggregation).

Any ``extra={...}`` fields passed to a log call are included in the output, so
operations can be logged with context (agent_id, session_id, ...).
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

# Standard ``LogRecord`` attributes; anything else on the record is treated as
# caller-supplied context and serialized into the JSON payload.
_RESERVED_RECORD_ATTRS = frozenset(logging.makeLogRecord({}).__dict__.keys() | {"message", "asctime", "taskName"})


class JsonLogFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Merge any caller-provided context (extra={...}).
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_ATTRS and not key.startswith("_"):
                payload[key] = value

        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", *, json_format: bool = False) -> None:
    """Configure the root logger.

    Safe to call multiple times; existing handlers are replaced.

    Args:
        level: Logging level name (e.g. ``"INFO"``, ``"DEBUG"``).
        json_format: When true, emit structured JSON logs instead of plain text.
    """
    handler = logging.StreamHandler(sys.stdout)
    if json_format:
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s | %(message)s"))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
