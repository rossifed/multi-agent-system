"""Unit tests for Claude backends."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_platform.config import Settings
from agent_platform.core.backends import (
    BackendError,
    BackendTimeoutError,
    ClaudeBackend,
    CliSubprocessBackend,
    MockBackend,
    build_backend,
)

pytestmark = pytest.mark.anyio

_GOOD_PAYLOAD = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "result": "hello there",
    "session_id": "sess-123",
    "usage": {"input_tokens": 10, "output_tokens": 2},
}


def _fake_process(stdout: bytes, stderr: bytes = b"", returncode: int = 0) -> MagicMock:
    process = MagicMock()
    process.communicate = AsyncMock(return_value=(stdout, stderr))
    process.returncode = returncode
    process.kill = MagicMock()
    process.wait = AsyncMock()
    return process


def _patch_exec(process: MagicMock | None = None, *, side_effect: type[Exception] | None = None):
    """Patch ``asyncio.create_subprocess_exec`` to return ``process`` or raise."""
    if side_effect is not None:
        return patch("asyncio.create_subprocess_exec", AsyncMock(side_effect=side_effect))
    return patch("asyncio.create_subprocess_exec", AsyncMock(return_value=process))


# --------------------------- MockBackend --------------------------- #


async def test_mock_backend_records_and_replies() -> None:
    backend = MockBackend(reply="echo")
    result = await backend.run("ping")
    assert result.text == "echo: ping"
    assert result.session_id == "mock-session-1"
    assert backend.calls == [("ping", None)]


async def test_mock_backend_preserves_resume_session() -> None:
    backend = MockBackend()
    result = await backend.run("again", resume_session_id="mock-session-1")
    assert result.session_id == "mock-session-1"


async def test_mock_backend_satisfies_protocol() -> None:
    assert isinstance(MockBackend(), ClaudeBackend)


# --------------------- CliSubprocessBackend ------------------------ #


def test_build_command_includes_flags() -> None:
    backend = CliSubprocessBackend(binary="claude", model="claude-opus-4-8")
    command = backend._build_command("hi", resume_session_id="abc")
    assert command[:5] == ["claude", "-p", "hi", "--output-format", "json"]
    assert "--model" in command and "claude-opus-4-8" in command
    assert "--resume" in command and "abc" in command


def test_build_command_omits_optional_flags() -> None:
    backend = CliSubprocessBackend(binary="claude")
    command = backend._build_command("hi", resume_session_id=None)
    assert "--model" not in command
    assert "--resume" not in command
    assert "--permission-mode" not in command
    assert "--add-dir" not in command
    assert "--allowedTools" not in command


def test_build_command_per_call_permission_mode_overrides_default() -> None:
    backend = CliSubprocessBackend(binary="claude", permission_mode="bypassPermissions")
    command = backend._build_command("hi", resume_session_id=None, permission_mode="plan")
    idx = command.index("--permission-mode")
    assert command[idx + 1] == "plan"  # per-call override wins over the instance default


def test_build_command_per_call_allowed_tools_overrides_default() -> None:
    backend = CliSubprocessBackend(binary="claude", allowed_tools="Bash Write")
    command = backend._build_command("hi", resume_session_id=None, allowed_tools="Read Grep")
    idx = command.index("--allowedTools")
    assert command[idx + 1 : idx + 3] == ["Read", "Grep"]  # per-call override wins


def test_build_command_includes_full_power_flags() -> None:
    backend = CliSubprocessBackend(
        binary="claude",
        permission_mode="bypassPermissions",
        workspace_dir="/work",
        allowed_tools="Bash Read Write",
    )
    command = backend._build_command("hi", resume_session_id=None)
    assert "--permission-mode" in command and "bypassPermissions" in command
    assert "--add-dir" in command and "/work" in command
    # allowed tools are split into individual args after the flag
    idx = command.index("--allowedTools")
    assert command[idx + 1 : idx + 4] == ["Bash", "Read", "Write"]


async def test_cli_run_success() -> None:
    backend = CliSubprocessBackend()
    process = _fake_process(json.dumps(_GOOD_PAYLOAD).encode())
    with _patch_exec(process):
        result = await backend.run("hi")
    assert result.text == "hello there"
    assert result.session_id == "sess-123"
    assert result.usage == {"input_tokens": 10, "output_tokens": 2}


async def test_cli_run_nonzero_exit_raises() -> None:
    backend = CliSubprocessBackend()
    process = _fake_process(b"", b"boom", returncode=1)
    with _patch_exec(process), pytest.raises(BackendError, match="exited with code 1"):
        await backend.run("hi")


async def test_cli_run_missing_binary_raises() -> None:
    backend = CliSubprocessBackend(binary="does-not-exist")
    with _patch_exec(side_effect=FileNotFoundError), pytest.raises(BackendError, match="not found"):
        await backend.run("hi")


async def test_cli_run_timeout_raises_and_kills() -> None:
    backend = CliSubprocessBackend(timeout_seconds=0.01)
    process = _fake_process(b"")
    with (
        _patch_exec(process),
        patch("asyncio.wait_for", AsyncMock(side_effect=asyncio.TimeoutError)),
        pytest.raises(BackendTimeoutError),
    ):
        await backend.run("hi")
    process.kill.assert_called_once()


async def test_cli_run_invalid_json_raises() -> None:
    backend = CliSubprocessBackend()
    process = _fake_process(b"not json")
    with _patch_exec(process), pytest.raises(BackendError, match="non-JSON"):
        await backend.run("hi")


async def test_cli_run_json_not_object_raises() -> None:
    backend = CliSubprocessBackend()
    process = _fake_process(b"[1, 2, 3]")
    with _patch_exec(process), pytest.raises(BackendError, match="not an object"):
        await backend.run("hi")


async def test_cli_run_is_error_flag_raises() -> None:
    backend = CliSubprocessBackend()
    payload = {"is_error": True, "subtype": "error_max_turns", "result": "x"}
    process = _fake_process(json.dumps(payload).encode())
    with _patch_exec(process), pytest.raises(BackendError, match="error_max_turns"):
        await backend.run("hi")


async def test_cli_run_missing_result_raises() -> None:
    backend = CliSubprocessBackend()
    payload = {"is_error": False, "session_id": "x"}
    process = _fake_process(json.dumps(payload).encode())
    with _patch_exec(process), pytest.raises(BackendError, match="missing a string 'result'"):
        await backend.run("hi")


# --------------------------- build_backend ------------------------- #


def test_build_backend_mock() -> None:
    assert isinstance(build_backend(Settings(backend="mock")), MockBackend)


def test_build_backend_cli() -> None:
    assert isinstance(build_backend(Settings(backend="cli")), CliSubprocessBackend)
