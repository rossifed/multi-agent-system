"""Inter-agent communication bus.

The bus is the Python-owned channel that lets participants (Claude agents or
humans via the web UI) exchange plain-text messages without coupling to a
terminal or the file system. See :mod:`agent_platform.bus.bus`.
"""

from __future__ import annotations

from agent_platform.bus.bus import MessageBus
from agent_platform.bus.models import BusMessage
from agent_platform.bus.store import FileMessageStore, InMemoryMessageStore, MessageStore

__all__ = [
    "BusMessage",
    "FileMessageStore",
    "InMemoryMessageStore",
    "MessageBus",
    "MessageStore",
]
