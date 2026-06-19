"""Interaction model.

An :class:`Interaction` is a single turn in an agent's conversation history -
either the user's prompt or the agent's response. Accumulated interactions form
the "outputs" of an agent.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class InteractionRole(StrEnum):
    """Who produced an interaction."""

    USER = "user"
    AGENT = "agent"


def _new_id() -> str:
    return f"msg-{uuid.uuid4()}"


def _now() -> datetime:
    return datetime.now(tz=UTC)


class Interaction(BaseModel):
    """A single prompt or response within an agent session."""

    id: str = Field(default_factory=_new_id)
    timestamp: datetime = Field(default_factory=_now)
    role: InteractionRole
    content: str
    # Token/usage metadata reported by the backend (agent turns only).
    usage: dict[str, object] | None = None
