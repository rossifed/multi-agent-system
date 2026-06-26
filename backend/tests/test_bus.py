"""Tests for the inter-agent message bus."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_platform.bus import BusMessage, FileMessageStore, InMemoryMessageStore, MessageBus
from agent_platform.bus.store import MessageStore


@pytest.fixture(params=["memory", "file"])
def bus(request: pytest.FixtureRequest, tmp_path: Path) -> MessageBus:
    """A bus over each store implementation, so every behavior is verified on both."""
    store: MessageStore
    store = InMemoryMessageStore() if request.param == "memory" else FileMessageStore(tmp_path / "bus.jsonl")
    return MessageBus(store)


def test_post_assigns_id_and_timestamp(bus: MessageBus) -> None:
    message = bus.post(content="hello", sender="agentA", recipient="agentB")
    assert message.id.startswith("bus-")
    assert message.sender == "agentA"
    assert message.recipient == "agentB"
    assert message.message_type == "text"
    assert message.content == "hello"
    assert message.timestamp is not None


def test_read_delivers_addressed_message_then_consumes_it(bus: MessageBus) -> None:
    bus.post(content="ping", sender="agentA", recipient="agentB")

    first = bus.read("agentB")
    assert [m.content for m in first] == ["ping"]

    # Reading again returns nothing — the message was consumed.
    assert bus.read("agentB") == []


def test_reader_never_receives_its_own_message(bus: MessageBus) -> None:
    bus.post(content="note to self", sender="agentA", recipient="agentA")
    assert bus.read("agentA") == []


def test_broadcast_is_delivered_to_everyone_but_the_sender(bus: MessageBus) -> None:
    bus.post(content="hi all", sender="agentA", recipient=None)
    bus.post(content="hi all too", sender="agentB", recipient="all")

    # agentA gets B's broadcast but not its own.
    assert [m.content for m in bus.read("agentA")] == ["hi all too"]
    # agentB gets A's broadcast but not its own.
    assert [m.content for m in bus.read("agentB")] == ["hi all"]


def test_message_not_addressed_to_reader_is_skipped(bus: MessageBus) -> None:
    bus.post(content="for C", sender="agentA", recipient="agentC")
    assert bus.read("agentB") == []


def test_history_returns_everything_without_consuming(bus: MessageBus) -> None:
    bus.post(content="m1", sender="agentA", recipient="agentB")
    bus.post(content="m2", sender="agentB", recipient="agentA")

    history = bus.history()
    assert [m.content for m in history] == ["m1", "m2"]
    # history does not consume: reads still work afterwards.
    assert [m.content for m in bus.read("agentB")] == ["m1"]


def test_history_filters_by_conversation(bus: MessageBus) -> None:
    bus.post(content="x", sender="a", recipient="b", conversation_id="conv-1")
    bus.post(content="y", sender="a", recipient="b", conversation_id="conv-2")
    assert [m.content for m in bus.history("conv-1")] == ["x"]


def test_human_and_agent_share_the_same_channel(bus: MessageBus) -> None:
    # The human participates exactly like an agent: post + read, no special case.
    bus.post(content="hello agent", sender="human", recipient="agentA")
    assert [m.content for m in bus.read("agentA")] == ["hello agent"]
    bus.post(content="hello human", sender="agentA", recipient="human")
    assert [m.content for m in bus.read("human")] == ["hello human"]


def test_json_round_trip_preserves_fields() -> None:
    message = BusMessage(content="c", sender="agentA", recipient="agentB", message_type="result")
    wire = message.model_dump(mode="json")
    assert wire["sender"] == "agentA"
    assert wire["recipient"] == "agentB"
    assert wire["message_type"] == "result"
    restored = BusMessage.model_validate_json(json.dumps(wire))
    assert restored.sender == "agentA"
    assert restored.recipient == "agentB"
    assert restored.message_type == "result"


def test_file_store_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "bus.jsonl"
    MessageBus(FileMessageStore(path)).post(content="durable", sender="agentA", recipient="agentB")

    # A fresh store over the same file sees the message and its consume-once state.
    reopened = MessageBus(FileMessageStore(path))
    assert [m.content for m in reopened.read("agentB")] == ["durable"]
    assert MessageBus(FileMessageStore(path)).read("agentB") == []
