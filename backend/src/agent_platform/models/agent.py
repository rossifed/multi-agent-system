"""Agent model.

In Phase 0 an "agent" is a named Claude Code session. The platform assigns it a
stable ``agent_id``; the underlying ``claude`` CLI session id is captured lazily
on the first message and reused (via ``--resume``) for subsequent turns.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from agent_platform.models.message import Interaction


class AgentStatus(StrEnum):
    """Lifecycle status of an agent session."""

    CREATED = "created"
    RUNNING = "running"
    ERROR = "error"


class AgentEngine(StrEnum):
    """How an agent's ``claude`` session is run — a per-agent choice, not a global."""

    HEADLESS = "headless"  # `claude -p` (structured, one-shot per turn)
    INTERACTIVE = "interactive"  # real interactive TUI driven over a PTY (Step 1)
    MOCK = "mock"  # canned responses (tests / offline)


class AgentConfig(BaseModel):
    """Per-agent launch configuration, chosen at creation (nothing hardcoded).

    Unset fields (``None``) fall back to server defaults when the backend is built.
    """

    engine: AgentEngine | None = None
    model: str | None = None
    permission_mode: str | None = None  # the agent's default mode (overridable per message)
    workspace_dir: str | None = None
    allowed_tools: str | None = None
    disallowed_tools: str | None = None


def _new_agent_id(name: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in name.strip().lower()).strip("-") or "agent"
    return f"{slug}-{uuid.uuid4().hex[:8]}"


def _now() -> datetime:
    return datetime.now(tz=UTC)


class Agent(BaseModel):
    """A managed Claude Code session."""

    agent_id: str
    name: str
    status: AgentStatus = AgentStatus.CREATED
    # The claude CLI session id, set after the first successful message.
    claude_session_id: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    outputs: list[Interaction] = Field(default_factory=list)
    config: AgentConfig = Field(default_factory=AgentConfig)

    @classmethod
    def create(cls, name: str, config: AgentConfig | None = None) -> Agent:
        """Build a fresh agent with a generated id.

        Args:
            name: Human-friendly agent name (e.g. ``"architect"``).
            config: Optional per-agent launch configuration (engine, model, …).

        Returns:
            A new :class:`Agent` in the ``created`` state.
        """
        return cls(agent_id=_new_agent_id(name), name=name, config=config or AgentConfig())

    def touch(self) -> None:
        """Update the ``updated_at`` timestamp to now."""
        self.updated_at = _now()

    def summary(self) -> dict[str, object]:
        """Return a compact dict for list/detail API responses (no outputs)."""
        return {
            "id": self.agent_id,
            "name": self.name,
            "status": self.status.value,
            "claude_session_id": self.claude_session_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "output_count": len(self.outputs),
            "config": self.config.model_dump(),
        }
