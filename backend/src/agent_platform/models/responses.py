"""Standard API response envelopes.

Every endpoint returns one of these shapes, per the development directives:

    Success: {"status": "success", "data": {...}, "timestamp": "..."}
    Error:   {"status": "error", "error": "...", "code": "...", "timestamp": "..."}
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(tz=UTC).isoformat()


class ApiSuccess(BaseModel, Generic[DataT]):
    """Successful API response envelope."""

    status: str = "success"
    data: DataT
    timestamp: str = Field(default_factory=utc_now_iso)


class ApiError(BaseModel):
    """Error API response envelope."""

    status: str = "error"
    error: str
    code: str
    timestamp: str = Field(default_factory=utc_now_iso)
