"""Unit tests for domain and response models."""

from __future__ import annotations

from agent_platform.models.agent import Agent, AgentStatus
from agent_platform.models.message import Interaction, InteractionRole
from agent_platform.models.responses import ApiError, ApiSuccess, utc_now_iso


def test_agent_create_generates_slugged_id() -> None:
    agent = Agent.create("My Architect")
    assert agent.agent_id.startswith("my-architect-")
    assert agent.status is AgentStatus.CREATED
    assert agent.outputs == []


def test_agent_create_handles_nonalnum_name() -> None:
    agent = Agent.create("!!!")
    assert agent.agent_id.startswith("agent-")


def test_agent_summary_excludes_outputs() -> None:
    agent = Agent.create("dev")
    agent.outputs.append(Interaction(role=InteractionRole.USER, content="hi"))
    summary = agent.summary()
    assert summary["output_count"] == 1
    assert "outputs" not in summary
    assert summary["id"] == agent.agent_id


def test_agent_touch_advances_timestamp() -> None:
    agent = Agent.create("dev")
    before = agent.updated_at
    agent.touch()
    assert agent.updated_at >= before


def test_interaction_defaults() -> None:
    interaction = Interaction(role=InteractionRole.AGENT, content="hello")
    assert interaction.id.startswith("msg-")
    assert interaction.usage is None


def test_api_success_envelope() -> None:
    envelope = ApiSuccess(data={"x": 1})
    assert envelope.status == "success"
    assert envelope.data == {"x": 1}
    assert envelope.timestamp


def test_api_error_envelope() -> None:
    envelope = ApiError(error="boom", code="X")
    assert envelope.status == "error"
    assert envelope.code == "X"


def test_utc_now_iso_returns_string() -> None:
    assert isinstance(utc_now_iso(), str)
