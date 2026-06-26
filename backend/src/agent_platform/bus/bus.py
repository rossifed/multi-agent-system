"""The message bus — the Python-owned communication channel.

Participants (Claude agents or humans via the web UI) only ever ``post`` and
``read``. They never know the transport: the bus delegates persistence to a
:class:`MessageStore`, so changing transport (file now, Redis later) leaves every
caller untouched. This is the decoupling the whole design rests on — an agent
emits a message without knowing where it goes or how it is delivered.
"""

from __future__ import annotations

from agent_platform.bus.models import BusMessage
from agent_platform.bus.store import MessageStore

# Recipient values that any reader is allowed to consume in addition to messages
# addressed to itself: an unaddressed message (router decides) and an explicit
# broadcast.
_BROADCAST_RECIPIENTS: frozenset[str | None] = frozenset({None, "all"})


class MessageBus:
    """Post and read messages through a pluggable store."""

    def __init__(self, store: MessageStore) -> None:
        """Initialize the bus.

        Args:
            store: The backing message store (transport).
        """
        self._store = store

    def post(
        self,
        *,
        content: str,
        sender: str,
        recipient: str | None = None,
        message_type: str = "text",
        conversation_id: str | None = None,
    ) -> BusMessage:
        """Emit a message onto the bus.

        Args:
            content: The message body as plain text.
            sender: The participant id emitting the message.
            recipient: Generic destination (participant id, topic, or ``None``).
            message_type: Free-form kind (``text``/``request``/``result``/``ack``).
            conversation_id: Optional grouping id (typically set by the orchestrator).

        Returns:
            The persisted :class:`BusMessage` (with its assigned id and timestamp).
        """
        message = BusMessage(
            content=content,
            sender=sender,
            recipient=recipient,
            message_type=message_type,
            conversation_id=conversation_id,
        )
        self._store.append(message)
        return message

    def read(self, reader: str) -> list[BusMessage]:
        """Return new messages for ``reader`` and mark them consumed.

        A message is delivered to ``reader`` when it is addressed to ``reader`` (or
        is a broadcast) and was not sent by ``reader`` itself. Reading consumes the
        message, so the same one is never returned twice to the same reader.

        Args:
            reader: The participant id reading its inbox.

        Returns:
            The list of newly delivered messages, in insertion order.
        """
        seen = self._store.seen_ids(reader)
        fresh: list[BusMessage] = []
        new_ids: set[str] = set()
        for message in self._store.all():
            if message.sender == reader:  # never deliver your own message back
                continue
            if message.recipient != reader and message.recipient not in _BROADCAST_RECIPIENTS:
                continue
            if message.id in seen:  # already consumed
                continue
            fresh.append(message)
            new_ids.add(message.id)
        self._store.mark_seen(reader, new_ids)
        return fresh

    def history(self, conversation_id: str | None = None) -> list[BusMessage]:
        """Return the full message log (for transparency / the web UI).

        Unlike :meth:`read`, this never consumes and includes every participant's
        messages — it is the observer view of the whole conversation.

        Args:
            conversation_id: When given, restrict to that conversation.

        Returns:
            All matching messages in insertion order.
        """
        messages = self._store.all()
        if conversation_id is None:
            return messages
        return [message for message in messages if message.conversation_id == conversation_id]
