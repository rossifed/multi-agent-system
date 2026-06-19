"""Session manager.

Manages Claude Code sessions ("agents"): creation, message routing, output
accumulation, and simple JSON-based persistence. Delegates the actual Claude
invocation to a :class:`~agent_platform.core.backends.ClaudeBackend`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from agent_platform.core.backends import BackendError, BackendTimeoutError, ClaudeBackend
from agent_platform.models.agent import Agent, AgentStatus
from agent_platform.models.message import Interaction, InteractionRole

logger = logging.getLogger(__name__)


class SessionNotFoundError(KeyError):
    """Raised when an operation targets an unknown agent id."""


class SessionManager:
    """Owns the lifecycle of agent sessions.

    Args:
        backend: The Claude backend used to fulfil messages.
        store_path: Optional path to a JSON file for persistence. When provided,
            state is loaded on construction and saved after every mutation.
    """

    def __init__(self, backend: ClaudeBackend, store_path: str | Path | None = None) -> None:
        self._backend = backend
        self._store_path = Path(store_path) if store_path else None
        self._agents: dict[str, Agent] = {}
        self._lock = asyncio.Lock()
        if self._store_path is not None:
            self._load()

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        """Load persisted agents from disk, if the store file exists."""
        assert self._store_path is not None
        if not self._store_path.exists():
            return
        try:
            raw = json.loads(self._store_path.read_text(encoding="utf-8"))
            for record in raw.get("agents", []):
                agent = Agent.model_validate(record)
                self._agents[agent.agent_id] = agent
            logger.info("Loaded persisted sessions", extra={"count": len(self._agents)})
        except (json.JSONDecodeError, ValueError) as exc:
            # A corrupt store should not crash startup; log and start empty.
            logger.error("Failed to load session store; starting empty: %s", exc)

    def _save(self) -> None:
        """Persist all agents to disk atomically (no-op if persistence disabled)."""
        if self._store_path is None:
            return
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"agents": [agent.model_dump(mode="json") for agent in self._agents.values()]}
        tmp = self._store_path.with_suffix(self._store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self._store_path)

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #
    def create_session(self, agent_name: str) -> str:
        """Create a new agent session.

        Args:
            agent_name: Human-friendly name for the agent.

        Returns:
            The generated ``agent_id``.

        Raises:
            ValueError: If ``agent_name`` is empty or whitespace.
        """
        if not agent_name or not agent_name.strip():
            raise ValueError("agent_name must not be empty")
        agent = Agent.create(agent_name.strip())
        self._agents[agent.agent_id] = agent
        self._save()
        logger.info("Created agent", extra={"agent_id": agent.agent_id, "agent_name": agent.name})
        return agent.agent_id

    def get_session(self, agent_id: str) -> dict[str, object]:
        """Return summary info for an agent.

        Args:
            agent_id: The agent identifier.

        Returns:
            A summary dict (see :meth:`Agent.summary`).

        Raises:
            SessionNotFoundError: If no such agent exists.
        """
        return self._require(agent_id).summary()

    def list_sessions(self) -> list[dict[str, object]]:
        """Return summaries for all known agents."""
        return [agent.summary() for agent in self._agents.values()]

    def get_outputs(self, agent_id: str) -> list[dict[str, object]]:
        """Return the accumulated interactions for an agent.

        Args:
            agent_id: The agent identifier.

        Returns:
            A list of interaction dicts in chronological order.

        Raises:
            SessionNotFoundError: If no such agent exists.
        """
        agent = self._require(agent_id)
        return [interaction.model_dump(mode="json") for interaction in agent.outputs]

    # ------------------------------------------------------------------ #
    # Messaging
    # ------------------------------------------------------------------ #
    async def send_message(self, agent_id: str, message: str) -> dict[str, object]:
        """Send a message to an agent and record the response.

        Returns a result envelope rather than raising, so callers get a uniform
        shape for both success and failure.

        Args:
            agent_id: Target agent.
            message: The user prompt.

        Returns:
            On success: ``{"status": "success", "agent_id", "response",
            "session_id", "usage"}``. On failure: ``{"status": "error", "code",
            "error", "agent_id"}``.
        """
        agent = self._agents.get(agent_id)
        if agent is None:
            logger.warning("Message to unknown agent", extra={"agent_id": agent_id})
            return {
                "status": "error",
                "code": "AGENT_NOT_FOUND",
                "error": f"No agent with id {agent_id!r}",
                "agent_id": agent_id,
            }

        async with self._lock:
            agent.outputs.append(Interaction(role=InteractionRole.USER, content=message))
            agent.status = AgentStatus.RUNNING
            agent.touch()

            try:
                result = await self._backend.run(message, resume_session_id=agent.claude_session_id)
            except BackendTimeoutError as exc:
                return self._fail(agent, "BACKEND_TIMEOUT", str(exc))
            except BackendError as exc:
                return self._fail(agent, "BACKEND_ERROR", str(exc))

            if result.session_id:
                agent.claude_session_id = result.session_id
            agent.outputs.append(Interaction(role=InteractionRole.AGENT, content=result.text, usage=result.usage))
            agent.status = AgentStatus.RUNNING
            agent.touch()
            self._save()

        logger.info(
            "Agent responded",
            extra={"agent_id": agent_id, "session_id": agent.claude_session_id},
        )
        return {
            "status": "success",
            "agent_id": agent_id,
            "response": result.text,
            "session_id": agent.claude_session_id,
            "usage": result.usage,
        }

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _require(self, agent_id: str) -> Agent:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise SessionNotFoundError(agent_id)
        return agent

    def _fail(self, agent: Agent, code: str, detail: str) -> dict[str, object]:
        """Mark an agent as errored, persist, and build an error envelope."""
        agent.status = AgentStatus.ERROR
        agent.touch()
        self._save()
        logger.error("Backend failure", extra={"agent_id": agent.agent_id, "code": code, "detail": detail})
        return {"status": "error", "code": code, "error": detail, "agent_id": agent.agent_id}
