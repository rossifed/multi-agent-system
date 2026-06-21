"""Unit tests for the SessionManager."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.core.backends import BackendError, BackendResult, BackendTimeoutError, MockBackend
from agent_platform.core.session_manager import SessionManager, SessionNotFoundError

pytestmark = pytest.mark.anyio


class _FailingBackend:
    """Backend that always raises the given exception."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def run(
        self,
        prompt: str,
        resume_session_id: str | None = None,
        permission_mode: str | None = None,
    ) -> BackendResult:
        raise self._exc


# ----------------------------- create ----------------------------- #


def test_create_session_returns_id(manager: SessionManager) -> None:
    agent_id = manager.create_session("architect")
    assert agent_id
    assert manager.get_session(agent_id)["name"] == "architect"


def test_create_session_rejects_empty_name(manager: SessionManager) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        manager.create_session("   ")


# --------------------------- queries ------------------------------- #


def test_get_session_unknown_raises(manager: SessionManager) -> None:
    with pytest.raises(SessionNotFoundError):
        manager.get_session("nope")


def test_list_sessions(manager: SessionManager) -> None:
    manager.create_session("a")
    manager.create_session("b")
    assert len(manager.list_sessions()) == 2


def test_get_outputs_unknown_raises(manager: SessionManager) -> None:
    with pytest.raises(SessionNotFoundError):
        manager.get_outputs("nope")


# --------------------------- messaging ----------------------------- #


async def test_send_message_success(manager: SessionManager) -> None:
    agent_id = manager.create_session("dev")
    result = await manager.send_message(agent_id, "Hello!")
    assert result["status"] == "success"
    assert result["response"] == "echo: Hello!"
    assert result["session_id"] == "mock-session-1"


async def test_send_message_records_outputs(manager: SessionManager) -> None:
    agent_id = manager.create_session("dev")
    await manager.send_message(agent_id, "Hello!")
    outputs = manager.get_outputs(agent_id)
    assert [o["role"] for o in outputs] == ["user", "agent"]


async def test_send_message_unknown_agent_returns_error(manager: SessionManager) -> None:
    result = await manager.send_message("nonexistent", "hello")
    assert result["status"] == "error"
    assert result["code"] == "AGENT_NOT_FOUND"


async def test_send_message_reuses_session_id_on_second_turn(manager: SessionManager) -> None:
    agent_id = manager.create_session("dev")
    first = await manager.send_message(agent_id, "turn 1")
    second = await manager.send_message(agent_id, "turn 2")
    assert first["session_id"] == second["session_id"]


async def test_send_message_backend_error(store_path: Path) -> None:
    manager = SessionManager(_FailingBackend(BackendError("kaboom")), store_path)
    agent_id = manager.create_session("dev")
    result = await manager.send_message(agent_id, "hi")
    assert result["status"] == "error"
    assert result["code"] == "BACKEND_ERROR"
    assert manager.get_session(agent_id)["status"] == "error"


async def test_send_message_backend_timeout(store_path: Path) -> None:
    manager = SessionManager(_FailingBackend(BackendTimeoutError("slow")), store_path)
    agent_id = manager.create_session("dev")
    result = await manager.send_message(agent_id, "hi")
    assert result["code"] == "BACKEND_TIMEOUT"


# --------------------------- persistence --------------------------- #


async def test_persistence_roundtrip(store_path: Path) -> None:
    manager = SessionManager(MockBackend(reply="echo"), store_path)
    agent_id = manager.create_session("dev")
    await manager.send_message(agent_id, "remember me")

    # A fresh manager pointed at the same store should recover state.
    reloaded = SessionManager(MockBackend(), store_path)
    assert reloaded.get_session(agent_id)["name"] == "dev"
    assert len(reloaded.get_outputs(agent_id)) == 2


def test_persistence_disabled_when_no_path() -> None:
    manager = SessionManager(MockBackend(), store_path=None)
    agent_id = manager.create_session("dev")
    assert manager.get_session(agent_id)["name"] == "dev"


def test_load_corrupt_store_starts_empty(store_path: Path) -> None:
    store_path.write_text("{ not valid json", encoding="utf-8")
    manager = SessionManager(MockBackend(), store_path)
    assert manager.list_sessions() == []
