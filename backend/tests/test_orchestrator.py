"""Tests for the orchestrator dispatch logic (no PTY involved)."""

from __future__ import annotations

from pathlib import Path

from agent_platform.bus import InMemoryMessageStore, MessageBus
from agent_platform.orchestrator import Orchestrator, select_pending, write_agent_mcp_config


def _bus() -> MessageBus:
    return MessageBus(InMemoryMessageStore())


def test_select_pending_picks_messages_addressed_to_managed_agents() -> None:
    bus = _bus()
    bus.post(content="hi", sender="human", recipient="agentA")
    bus.post(content="for B", sender="human", recipient="agentB")  # not managed
    bus.post(content="from agent", sender="agentA", recipient="human")  # our own output

    pending = select_pending(bus.history(), managed={"agentA"}, dispatched=set())
    assert [m.content for m in pending] == ["hi"]


def test_select_pending_skips_already_dispatched() -> None:
    bus = _bus()
    message = bus.post(content="hi", sender="human", recipient="agentA")
    pending = select_pending(bus.history(), {"agentA"}, dispatched={message.id})
    assert pending == []


class FakeAgent:
    """A waker that simulates the agent replying on the bus when woken."""

    def __init__(self, bus: MessageBus, agent_id: str, reply_on: str = "wake") -> None:
        self._bus = bus
        self._agent_id = agent_id
        self._reply_on = reply_on  # "wake" or "submit"
        self.wakes = 0
        self.submits = 0

    def wake(self, text: str) -> None:
        self.wakes += 1
        if self._reply_on == "wake":
            self._reply()

    def submit(self) -> None:
        self.submits += 1
        if self._reply_on == "submit":
            self._reply()

    def _reply(self) -> None:
        self._bus.post(content="reply", sender=self._agent_id, recipient="human")


def test_seed_marks_existing_history_so_it_is_not_replayed() -> None:
    bus = _bus()
    bus.post(content="old", sender="human", recipient="agentA")
    orch = Orchestrator(bus, {"agentA": FakeAgent(bus, "agentA")})
    orch.seed()
    # Nothing new since seed -> nothing to dispatch.
    assert orch.tick(poll_interval=0) is None


def test_tick_wakes_target_and_detects_reply() -> None:
    bus = _bus()
    agent = FakeAgent(bus, "agentA", reply_on="wake")
    orch = Orchestrator(bus, {"agentA": agent})
    bus.post(content="hello agent", sender="human", recipient="agentA")

    woken = orch.tick(poll_interval=0)
    assert woken == "agentA"
    assert agent.wakes == 1
    assert agent.submits == 0
    assert [m.content for m in bus.history()] == ["hello agent", "reply"]


def test_tick_retries_with_submit_when_first_wake_is_silent() -> None:
    bus = _bus()
    agent = FakeAgent(bus, "agentA", reply_on="submit")  # only replies after submit
    orch = Orchestrator(bus, {"agentA": agent})
    bus.post(content="hello", sender="human", recipient="agentA")

    woken = orch.tick(wait_timeout=0.05, poll_interval=0)
    assert woken == "agentA"
    assert agent.wakes == 1
    assert agent.submits == 1  # the retry fired and produced the reply


def test_tick_returns_none_when_nothing_pending() -> None:
    bus = _bus()
    orch = Orchestrator(bus, {"agentA": FakeAgent(bus, "agentA")})
    assert orch.tick(poll_interval=0) is None


def test_write_agent_mcp_config_emits_expected_shape(tmp_path: Path) -> None:
    import json

    path = write_agent_mcp_config(tmp_path, "agentA", tmp_path / "bus.jsonl", "conv-1")
    config = json.loads(path.read_text())
    server = config["mcpServers"]["bus"]
    assert server["args"] == ["-m", "agent_platform.bus.mcp_server"]
    assert server["env"]["AGENT_ID"] == "agentA"
    assert server["env"]["CONVERSATION_ID"] == "conv-1"
    assert server["env"]["BUS_FILE"].endswith("bus.jsonl")
