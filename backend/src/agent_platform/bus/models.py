"""Bus message model.

A :class:`BusMessage` is one message exchanged on the bus between *participants*.
A participant is anything that can post and read: a Claude agent OR a human via
the web UI. The message is the unit the Python-owned channel transports — agents
never print to a terminal, they emit a message.

`recipient` is a GENERIC destination, not necessarily an agent: another
participant id, a topic (pub/sub), or ``None`` to let the router decide.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field


def _new_id() -> str:
    return f"bus-{uuid.uuid4()}"


def _now() -> datetime:
    return datetime.now(tz=UTC)


class BusMessage(BaseModel):
    """A single message on the bus.

    Attributes:
        id: Unique message id (assigned by the bus, never by the sender).
        timestamp: UTC creation time.
        conversation_id: Groups messages of one exchange (set by the orchestrator).
        message_type: Free-form kind, e.g. ``text``/``request``/``result``/``ack``.
        sender: Participant id that emitted the message.
        recipient: Generic destination (participant id, topic, or ``None``).
        content: The message body as plain text.
    """

    id: str = Field(default_factory=_new_id)
    timestamp: datetime = Field(default_factory=_now)
    conversation_id: str | None = None
    message_type: str = "text"
    sender: str
    recipient: str | None = None
    content: str
