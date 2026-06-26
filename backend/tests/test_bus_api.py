"""Tests for the bus API routes (human-as-participant + SSE stream)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from agent_platform.api.bus_routes import _sse_format, _stream_events, stream
from agent_platform.api.main import create_app
from agent_platform.bus import BusMessage, InMemoryMessageStore, MessageBus


@pytest.fixture
def bus() -> MessageBus:
    return MessageBus(InMemoryMessageStore())


@pytest.fixture
def client(bus: MessageBus) -> TestClient:
    # Inject an in-memory bus. The bus routes never touch the session manager, and the
    # bus is set eagerly in create_app, so no real backend or lifespan is needed.
    app = create_app(bus=bus)
    return TestClient(app)


def test_post_message_stores_and_returns_envelope(client: TestClient, bus: MessageBus) -> None:
    response = client.post("/bus/post", json={"content": "hello agent", "recipient": "agentA"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["data"]["content"] == "hello agent"
    assert body["data"]["sender"] == "human"  # default participant
    assert body["data"]["recipient"] == "agentA"
    assert [m.content for m in bus.history()] == ["hello agent"]


def test_post_message_rejects_empty_content(client: TestClient) -> None:
    assert client.post("/bus/post", json={"content": ""}).status_code == 400


def test_history_returns_full_conversation(client: TestClient, bus: MessageBus) -> None:
    bus.post(content="m1", sender="agentA", recipient="human")
    bus.post(content="m2", sender="human", recipient="agentA")

    body = client.get("/bus/history").json()
    assert body["data"]["count"] == 2
    assert [m["content"] for m in body["data"]["messages"]] == ["m1", "m2"]


def test_history_filters_by_conversation(client: TestClient, bus: MessageBus) -> None:
    bus.post(content="x", sender="agentA", recipient="human", conversation_id="c1")
    bus.post(content="y", sender="agentA", recipient="human", conversation_id="c2")

    body = client.get("/bus/history", params={"conversation_id": "c1"}).json()
    assert [m["content"] for m in body["data"]["messages"]] == ["x"]


def test_sse_format_encodes_one_event() -> None:
    message = BusMessage(content="hi", sender="agentA", recipient="human")
    frame = _sse_format(message)
    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    assert json.loads(frame[len("data: ") :])["content"] == "hi"


@pytest.mark.anyio
async def test_stream_events_emits_new_messages_then_stops(bus: MessageBus) -> None:
    bus.post(content="first", sender="agentA", recipient="human")

    async def never_disconnected() -> bool:
        return False

    frames = [
        frame
        async for frame in _stream_events(bus, never_disconnected, poll_interval=0, max_polls=1)
    ]
    assert len(frames) == 1
    assert json.loads(frames[0][len("data: ") :])["content"] == "first"


@pytest.mark.anyio
async def test_stream_events_stops_on_disconnect(bus: MessageBus) -> None:
    bus.post(content="ignored", sender="agentA", recipient="human")

    async def already_disconnected() -> bool:
        return True

    frames = [frame async for frame in _stream_events(bus, already_disconnected, poll_interval=0)]
    assert frames == []


@pytest.mark.anyio
async def test_stream_events_polls_then_disconnects(bus: MessageBus) -> None:
    # Stays connected for the first poll (covers the sleep path), then disconnects.
    calls = {"n": 0}

    async def disconnect_after_first() -> bool:
        connected = calls["n"] > 0
        calls["n"] += 1
        return connected

    bus.post(content="m", sender="agentA", recipient="human")
    frames = [frame async for frame in _stream_events(bus, disconnect_after_first, poll_interval=0)]
    assert [json.loads(f[len("data: ") :])["content"] for f in frames] == ["m"]


@pytest.mark.anyio
async def test_stream_route_returns_event_stream(bus: MessageBus) -> None:
    async def disconnected() -> bool:
        return True

    fake_request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(bus_stream_poll_seconds=0.0)),
        is_disconnected=disconnected,
    )
    response = stream(cast(Request, fake_request), bus)
    assert response.media_type == "text/event-stream"
    chunks = [chunk async for chunk in response.body_iterator]
    assert chunks == []
