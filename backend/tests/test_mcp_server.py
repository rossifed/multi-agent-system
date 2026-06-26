"""Tests for the bus MCP server handlers."""

from __future__ import annotations

from agent_platform.bus import InMemoryMessageStore, MessageBus
from agent_platform.bus.mcp_server import create_server, post, read


def _bus() -> MessageBus:
    return MessageBus(InMemoryMessageStore())


def test_post_emits_and_acknowledges() -> None:
    bus = _bus()
    ack = post(bus, "agentA", "conv-1", "hello", to="agentB", message_type="text")
    assert ack == "posted (text) to agentB"
    assert [m.content for m in bus.history()] == ["hello"]
    stored = bus.history()[0]
    assert stored.sender == "agentA"
    assert stored.recipient == "agentB"
    assert stored.conversation_id == "conv-1"


def test_post_without_recipient_omits_destination_in_ack() -> None:
    ack = post(_bus(), "agentA", None, "broadcast", to=None)
    assert ack == "posted (text)"


def test_read_returns_dicts_and_consumes() -> None:
    bus = _bus()
    post(bus, "agentA", None, "ping", to="agentB")

    received = read(bus, "agentB")
    assert len(received) == 1
    assert received[0]["content"] == "ping"
    assert received[0]["sender"] == "agentA"
    # Consumed: a second read returns nothing.
    assert read(bus, "agentB") == []


def test_create_server_registers_both_tools() -> None:
    server = create_server(_bus(), "agentA", "conv-1")
    assert server.name == "bus"
