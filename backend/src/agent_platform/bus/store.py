"""Message stores — the swappable transport behind the bus.

The :class:`MessageStore` protocol is the seam that decouples participants from
*how* messages are persisted/transported. Callers (the bus) never depend on the
concrete store, so swapping :class:`FileMessageStore` for a future Redis store
changes the transport without touching agents or the API.

A store does two things: persist the append-only message log, and track, per
reader, which message ids that reader has already consumed (so each message is
delivered once).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from agent_platform.bus.models import BusMessage


@runtime_checkable
class MessageStore(Protocol):
    """Protocol implemented by every message store."""

    def append(self, message: BusMessage) -> None:
        """Persist a new message."""
        ...

    def all(self) -> list[BusMessage]:
        """Return every message in insertion order."""
        ...

    def seen_ids(self, reader: str) -> set[str]:
        """Return the set of message ids ``reader`` has already consumed."""
        ...

    def mark_seen(self, reader: str, ids: set[str]) -> None:
        """Record ``ids`` as consumed by ``reader``."""
        ...


class FileMessageStore:
    """JSONL-backed store, shared across processes on a single host.

    One JSON line per message; one ``<stem>.<reader>.seen`` companion file per
    reader holding consumed ids. Append-only writes make it safe enough for the
    MCP server process and the web backend to share the same file. Swap for a
    Redis store for multi-host / high-throughput.
    """

    def __init__(self, path: str | Path) -> None:
        """Initialize the store.

        Args:
            path: Path to the JSONL bus file. Parent dirs are created if missing.
        """
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, message: BusMessage) -> None:
        """See :meth:`MessageStore.append`."""
        line = json.dumps(message.model_dump(mode="json"), ensure_ascii=False)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def all(self) -> list[BusMessage]:
        """See :meth:`MessageStore.all`."""
        if not self._path.exists():
            return []
        messages: list[BusMessage] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                messages.append(BusMessage.model_validate_json(line))
        return messages

    def _seen_path(self, reader: str) -> Path:
        return self._path.parent / f"{self._path.stem}.{reader}.seen"

    def seen_ids(self, reader: str) -> set[str]:
        """See :meth:`MessageStore.seen_ids`."""
        path = self._seen_path(reader)
        return set(path.read_text(encoding="utf-8").split()) if path.exists() else set()

    def mark_seen(self, reader: str, ids: set[str]) -> None:
        """See :meth:`MessageStore.mark_seen`."""
        if not ids:
            return
        merged = self.seen_ids(reader) | ids
        self._seen_path(reader).write_text("\n".join(sorted(merged)), encoding="utf-8")


class InMemoryMessageStore:
    """Non-persistent store for tests and single-process demos."""

    def __init__(self) -> None:
        self._messages: list[BusMessage] = []
        self._seen: dict[str, set[str]] = {}

    def append(self, message: BusMessage) -> None:
        """See :meth:`MessageStore.append`."""
        self._messages.append(message)

    def all(self) -> list[BusMessage]:
        """See :meth:`MessageStore.all`."""
        return list(self._messages)

    def seen_ids(self, reader: str) -> set[str]:
        """See :meth:`MessageStore.seen_ids`."""
        return set(self._seen.get(reader, set()))

    def mark_seen(self, reader: str, ids: set[str]) -> None:
        """See :meth:`MessageStore.mark_seen`."""
        if ids:
            self._seen.setdefault(reader, set()).update(ids)
