"""Claude backends.

A backend is the thing that actually turns a prompt into a response. The platform
talks to it through the :class:`ClaudeBackend` protocol, so the rest of the code
never depends on *how* Claude is reached.

Implementations:
- :class:`CliSubprocessBackend` - drives the local ``claude`` CLI in headless mode
  (``claude -p ... --output-format json``). This authenticates via the host's
  Claude subscription (Max) OAuth credentials and does NOT consume API credits.
  Multi-turn context is preserved with ``--resume <session_id>``.
- :class:`MockBackend` - returns canned responses with no external process; used
  for tests, demos, and offline development.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from agent_platform.config import Settings

if TYPE_CHECKING:
    from agent_platform.models.agent import AgentConfig

logger = logging.getLogger(__name__)


class BackendError(RuntimeError):
    """Raised when the backend fails to produce a valid response."""


class BackendTimeoutError(BackendError):
    """Raised when the backend exceeds its configured timeout."""


@dataclass(slots=True)
class BackendResult:
    """Outcome of a single backend invocation.

    Attributes:
        text: The agent's textual response.
        session_id: Backend session id, used to resume the conversation.
        usage: Token/usage metadata reported by the backend, if any.
    """

    text: str
    session_id: str | None
    usage: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class ClaudeBackend(Protocol):
    """Protocol implemented by every Claude backend."""

    async def run(
        self,
        prompt: str,
        resume_session_id: str | None = None,
        permission_mode: str | None = None,
        allowed_tools: str | None = None,
        disallowed_tools: str | None = None,
    ) -> BackendResult:
        """Send ``prompt`` to Claude and return the response.

        Args:
            prompt: The user message to send.
            resume_session_id: When provided, resume that session so prior context
                is available; otherwise start a fresh session.
            permission_mode: Per-call override of the agent's permission mode (e.g.
                ``"plan"`` to plan without acting, ``"bypassPermissions"`` for full
                execution). When ``None``, the backend's configured default is used.

        Returns:
            The parsed :class:`BackendResult`.

        Raises:
            BackendError: If the backend fails or returns an unparseable response.
            BackendTimeoutError: If the invocation exceeds the configured timeout.
        """
        ...

    def run_stream(
        self,
        prompt: str,
        resume_session_id: str | None = None,
        permission_mode: str | None = None,
        allowed_tools: str | None = None,
        disallowed_tools: str | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        """Stream the agent's progress as compact UI events.

        Yields dicts shaped like ``{"type": "text"|"tool"|"result"|"error", ...}``
        as the agent works, so callers can render progress live. The final
        ``result`` event carries ``session_id`` and ``usage``.
        """
        ...


class CliSubprocessBackend:
    """Backend that drives the ``claude`` CLI as a subprocess.

    Uses headless JSON mode so the response can be parsed deterministically.
    """

    def __init__(
        self,
        binary: str = "claude",
        timeout_seconds: float = 120.0,
        model: str | None = None,
        permission_mode: str | None = None,
        workspace_dir: str | None = None,
        allowed_tools: str | None = None,
    ) -> None:
        """Initialize the backend.

        Args:
            binary: Path to the ``claude`` executable.
            timeout_seconds: Hard timeout for a single invocation.
            model: Optional model override passed via ``--model``.
            permission_mode: ``--permission-mode`` value. ``"bypassPermissions"``
                gives the agent full power (runs tools with no approval), making
                it behave like a local terminal session. Must be gated by our own
                authentication and a scoped workspace.
            workspace_dir: Directory the agent runs in and is granted access to
                (``--add-dir``); also the subprocess cwd. Scopes file access.
            allowed_tools: Space-separated tool allowlist (``--allowedTools``).
                ``None`` leaves the CLI default (all tools, subject to permission mode).
        """
        self._binary = binary
        self._timeout = timeout_seconds
        self._model = model
        self._permission_mode = permission_mode
        self._workspace_dir = workspace_dir
        self._allowed_tools = allowed_tools

    def _build_command(
        self,
        prompt: str,
        resume_session_id: str | None,
        permission_mode: str | None = None,
        allowed_tools: str | None = None,
        output_format: str = "json",
        disallowed_tools: str | None = None,
    ) -> list[str]:
        mode = permission_mode or self._permission_mode
        tools = allowed_tools or self._allowed_tools
        command = [self._binary, "-p", prompt, "--output-format", output_format]
        if output_format == "stream-json":
            command += ["--verbose"]  # required by the CLI for -p stream-json
        if self._model:
            command += ["--model", self._model]
        if mode:
            command += ["--permission-mode", mode]
        if tools:
            command += ["--allowedTools", *tools.split()]
        if disallowed_tools:
            command += ["--disallowedTools", *disallowed_tools.split()]
        if self._workspace_dir:
            command += ["--add-dir", self._workspace_dir]
        if resume_session_id:
            command += ["--resume", resume_session_id]
        return command

    async def run(
        self,
        prompt: str,
        resume_session_id: str | None = None,
        permission_mode: str | None = None,
        allowed_tools: str | None = None,
        disallowed_tools: str | None = None,
    ) -> BackendResult:
        """See :meth:`ClaudeBackend.run`."""
        command = self._build_command(
            prompt, resume_session_id, permission_mode, allowed_tools, disallowed_tools=disallowed_tools
        )
        logger.debug("Invoking claude CLI", extra={"resume": resume_session_id, "model": self._model})

        cwd = None
        if self._workspace_dir:
            os.makedirs(self._workspace_dir, exist_ok=True)
            cwd = self._workspace_dir

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
        except FileNotFoundError as exc:
            raise BackendError(f"claude binary not found: {self._binary!r}") from exc

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self._timeout)
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise BackendTimeoutError(f"claude CLI timed out after {self._timeout}s") from exc

        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()
            raise BackendError(f"claude CLI exited with code {process.returncode}: {detail}")

        return self._parse_output(stdout)

    async def run_stream(
        self,
        prompt: str,
        resume_session_id: str | None = None,
        permission_mode: str | None = None,
        allowed_tools: str | None = None,
        disallowed_tools: str | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        """Stream the agent's progress as it works (see :meth:`ClaudeBackend.run_stream`)."""
        command = self._build_command(
            prompt,
            resume_session_id,
            permission_mode,
            allowed_tools,
            output_format="stream-json",
            disallowed_tools=disallowed_tools,
        )
        cwd = None
        if self._workspace_dir:
            os.makedirs(self._workspace_dir, exist_ok=True)
            cwd = self._workspace_dir

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
        except FileNotFoundError as exc:
            raise BackendError(f"claude binary not found: {self._binary!r}") from exc

        assert process.stdout is not None
        assert process.stderr is not None
        try:
            while True:
                try:
                    raw = await asyncio.wait_for(process.stdout.readline(), timeout=self._timeout)
                except TimeoutError:
                    yield {"type": "error", "error": f"stream stalled after {self._timeout}s"}
                    break
                if not raw:
                    break  # EOF
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for ui in self._to_ui_events(event):
                    yield ui
            await process.wait()
            if process.returncode not in (0, None):
                detail = (await process.stderr.read()).decode("utf-8", errors="replace").strip()
                yield {"type": "error", "error": f"claude CLI exited with code {process.returncode}: {detail[:200]}"}
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    @staticmethod
    def _to_ui_events(event: dict[str, object]) -> list[dict[str, object]]:
        """Translate a raw stream-json event into zero or more compact UI events."""
        etype = event.get("type")
        out: list[dict[str, object]] = []
        if etype == "assistant":
            message = event.get("message")
            content = message.get("content", []) if isinstance(message, dict) else []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and block.get("text"):
                    out.append({"type": "text", "text": block["text"]})
                elif block.get("type") == "tool_use":
                    raw_input = block.get("input")
                    summary = json.dumps(raw_input)[:160] if raw_input is not None else ""
                    out.append({"type": "tool", "name": block.get("name", "tool"), "input": summary})
        elif etype == "result":
            out.append(
                {
                    "type": "result",
                    "text": event.get("result", "") if isinstance(event.get("result"), str) else "",
                    "session_id": event.get("session_id"),
                    "usage": event.get("usage") if isinstance(event.get("usage"), dict) else {},
                }
            )
        return out

    @staticmethod
    def _parse_output(stdout: bytes) -> BackendResult:
        raw = stdout.decode("utf-8", errors="replace").strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BackendError(f"claude CLI returned non-JSON output: {raw[:200]!r}") from exc

        if not isinstance(payload, dict):
            raise BackendError("claude CLI JSON output was not an object")

        if payload.get("is_error"):
            subtype = payload.get("subtype", "unknown")
            raise BackendError(f"claude CLI reported an error (subtype={subtype})")

        text = payload.get("result")
        if not isinstance(text, str):
            raise BackendError("claude CLI output missing a string 'result' field")

        session_id = payload.get("session_id")
        usage = payload.get("usage")
        return BackendResult(
            text=text,
            session_id=session_id if isinstance(session_id, str) else None,
            usage=usage if isinstance(usage, dict) else {},
        )


class MockBackend:
    """In-memory backend with deterministic, canned responses.

    Records every call for assertions and never touches the network or filesystem.
    """

    def __init__(self, reply: str = "mock response") -> None:
        """Initialize the mock.

        Args:
            reply: Static text returned for every prompt.
        """
        self._reply = reply
        self._counter = 0
        self.calls: list[tuple[str, str | None]] = []

    async def run(
        self,
        prompt: str,
        resume_session_id: str | None = None,
        permission_mode: str | None = None,
        allowed_tools: str | None = None,
        disallowed_tools: str | None = None,
    ) -> BackendResult:
        """See :meth:`ClaudeBackend.run`. Returns a canned response."""
        self.calls.append((prompt, resume_session_id))
        # Keep an existing session id stable across turns; mint one on first use.
        if resume_session_id is None:
            self._counter += 1
            session_id = f"mock-session-{self._counter}"
        else:
            session_id = resume_session_id
        return BackendResult(
            text=f"{self._reply}: {prompt}",
            session_id=session_id,
            usage={"input_tokens": 0, "output_tokens": 0},
        )

    async def run_stream(
        self,
        prompt: str,
        resume_session_id: str | None = None,
        permission_mode: str | None = None,
        allowed_tools: str | None = None,
        disallowed_tools: str | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        """See :meth:`ClaudeBackend.run_stream`. Emits a couple of canned events."""
        self.calls.append((prompt, resume_session_id))
        session_id = resume_session_id or f"mock-session-{len(self.calls)}"
        yield {"type": "text", "text": f"{self._reply}: {prompt}"}
        yield {
            "type": "result",
            "text": f"{self._reply}: {prompt}",
            "session_id": session_id,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }


def build_backend(settings: Settings) -> ClaudeBackend:
    """Construct the backend selected by configuration.

    Args:
        settings: Application settings.

    Returns:
        A configured :class:`ClaudeBackend` implementation.
    """
    if settings.backend == "mock":
        logger.info("Using MockBackend (no real Claude invocation)")
        return MockBackend()
    return CliSubprocessBackend(
        binary=settings.claude_binary,
        timeout_seconds=settings.claude_timeout_seconds,
        model=settings.claude_model,
        permission_mode=settings.claude_permission_mode,
        workspace_dir=settings.claude_workspace_dir,
        allowed_tools=settings.claude_allowed_tools,
    )


def build_backend_for_config(config: AgentConfig, settings: Settings) -> ClaudeBackend:
    """Build the backend an agent asked for via its per-agent config.

    The agent's ``engine`` (interactive / headless / mock) and per-agent overrides
    (model, workspace, permission mode, tools) decide what is built; unset fields
    fall back to server defaults. The global ``AGENT_BACKEND=mock`` switch still
    wins, for offline/test runs.
    """
    from agent_platform.models.agent import AgentEngine

    if settings.backend == "mock":
        return MockBackend()

    engine = config.engine or AgentEngine.HEADLESS
    if engine == AgentEngine.MOCK:
        return MockBackend()
    if engine == AgentEngine.INTERACTIVE:
        from agent_platform.core.interactive_backend import InteractiveBackend

        return InteractiveBackend(
            binary=settings.claude_binary,
            timeout_seconds=settings.claude_timeout_seconds,
            model=config.model or settings.claude_model,
            workspace_dir=config.workspace_dir or settings.claude_workspace_dir,
        )
    return CliSubprocessBackend(
        binary=settings.claude_binary,
        timeout_seconds=settings.claude_timeout_seconds,
        model=config.model or settings.claude_model,
        permission_mode=config.permission_mode or settings.claude_permission_mode,
        workspace_dir=config.workspace_dir or settings.claude_workspace_dir,
        allowed_tools=config.allowed_tools or settings.claude_allowed_tools,
    )
