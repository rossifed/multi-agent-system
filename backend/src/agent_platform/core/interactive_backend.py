"""Interactive ("PTY") Claude backend — engine=interactive.

Drives the REAL interactive ``claude`` TUI over a pseudo-terminal (the Step 1
approach), instead of ``claude -p``. This is a *choice* an agent can make at
creation, not a global default. A persistent ``claude`` process is kept alive per
backend instance, so multi-turn context comes from the live session itself.

v1 scope: the session runs full-power (no interactive approval relay yet — that
is a follow-up), and ``run_stream`` returns the final reply as events rather than
true token-level streaming. The point of v1 is to validate the interactive engine
end-to-end as a selectable option.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from collections.abc import AsyncIterator

import pexpect
import pyte

from agent_platform.core.backends import BackendError, BackendResult

logger = logging.getLogger(__name__)


class InteractiveBackend:
    """Backend that drives a persistent interactive ``claude`` session via a PTY."""

    def __init__(
        self,
        binary: str = "claude",
        timeout_seconds: float = 180.0,
        model: str | None = None,
        workspace_dir: str | None = None,
        cols: int = 120,
        rows: int = 50,
    ) -> None:
        self._binary = binary
        self._timeout = timeout_seconds
        self._model = model
        self._workspace_dir = workspace_dir
        self._cols = cols
        self._rows = rows
        self._child: pexpect.spawn | None = None
        self._screen = pyte.Screen(cols, rows)
        self._stream = pyte.Stream(self._screen)
        self._lock = threading.Lock()  # one turn at a time on the live session

    # --- lifecycle (sync, run inside a thread) ---------------------------
    def _ensure_started(self) -> None:
        if self._child is not None and self._child.isalive():
            return
        cwd = None
        if self._workspace_dir:
            os.makedirs(self._workspace_dir, exist_ok=True)
            cwd = self._workspace_dir
        args = ["--permission-mode", "bypassPermissions"]
        if self._model:
            args += ["--model", self._model]
        logger.info("Starting interactive claude session", extra={"model": self._model})
        try:
            self._child = pexpect.spawn(
                self._binary,
                args=args,
                cwd=cwd,
                encoding="utf-8",
                dimensions=(self._rows, self._cols),
                timeout=self._timeout,
            )
        except pexpect.ExceptionPexpect as exc:
            raise BackendError(f"failed to start interactive claude: {exc}") from exc
        self._wait_stable(min_secs=6.0, stable_secs=2.0)
        self._clear_startup_prompts()

    def _clear_startup_prompts(self) -> None:
        """Answer the interactive startup prompts so the session is ready for input.

        Two may chain on first run:
          - "Is this a project you trust?" — default is "Yes, I trust" → Enter.
          - "WARNING: Bypass Permissions mode" — default is "No, exit", so we
            move down to "Yes, I accept" then Enter.
        Once accepted they are remembered under CLAUDE_CONFIG_DIR. In a sandbox
        (IS_SANDBOX=1) the bypass warning is typically skipped entirely.
        """
        assert self._child is not None
        for _ in range(4):  # a couple of prompts may appear in sequence
            screen = self._render().lower()
            if "trust this folder" in screen or "safety check" in screen:
                self._child.send("\r")  # default highlighted = "Yes, I trust this folder"
            elif "bypass permissions mode" in screen and "yes, i accept" in screen:
                self._child.send("\x1b[B")  # arrow down to "Yes, I accept"
                time.sleep(0.2)
                self._child.send("\r")
            else:
                return  # no known prompt left → main UI is ready
            self._wait_stable(min_secs=1.5, stable_secs=1.5)

    def close(self) -> None:
        if self._child is None:
            return
        try:
            self._child.sendcontrol("c")
            time.sleep(0.2)
            self._child.terminate(force=True)
        except Exception:
            pass
        self._child = None

    # --- screen helpers --------------------------------------------------
    def _pump(self, duration: float) -> None:
        assert self._child is not None
        end = time.time() + duration
        while time.time() < end:
            try:
                data = self._child.read_nonblocking(size=65536, timeout=0.3)
            except pexpect.TIMEOUT:
                break
            except pexpect.EOF:
                break
            if data:
                self._stream.feed(data)

    def _wait_stable(self, min_secs: float, stable_secs: float) -> None:
        start = time.time()
        self._pump(min_secs)
        last = self._render()
        last_change = time.time()
        while time.time() - start < self._timeout:
            self._pump(0.5)
            now = self._render()
            if now != last:
                last, last_change = now, time.time()
            elif time.time() - last_change >= stable_secs:
                return

    def _render(self) -> str:
        return "\n".join(self._screen.display)

    def _assistant_lines(self) -> list[str]:
        lines = []
        for raw in self._screen.display:
            stripped = raw.rstrip().lstrip()
            if stripped.startswith("●"):
                cleaned = stripped.lstrip("●").strip()
                if cleaned:
                    lines.append(cleaned)
        return lines

    # --- blocking turn ---------------------------------------------------
    def _send_sync(self, prompt: str) -> str:
        with self._lock:
            self._ensure_started()
            assert self._child is not None
            before = set(self._assistant_lines())
            self._child.send(prompt)
            time.sleep(0.4)
            self._child.send("\r")
            self._wait_stable(min_secs=2.0, stable_secs=3.0)
            after = self._assistant_lines()
            fresh = [ln for ln in after if ln not in before]
            return "\n".join(fresh).strip() or "\n".join(after[-3:]).strip()

    # --- ClaudeBackend protocol -----------------------------------------
    async def run(
        self,
        prompt: str,
        resume_session_id: str | None = None,
        permission_mode: str | None = None,
        allowed_tools: str | None = None,
        disallowed_tools: str | None = None,
    ) -> BackendResult:
        """Send a turn to the live interactive session and return its reply."""
        text = await asyncio.to_thread(self._send_sync, prompt)
        # The persistent session carries continuity, so there is no resume id.
        return BackendResult(text=text, session_id=None, usage={})

    async def run_stream(
        self,
        prompt: str,
        resume_session_id: str | None = None,
        permission_mode: str | None = None,
        allowed_tools: str | None = None,
        disallowed_tools: str | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        """v1: run the turn, then emit the reply as text + result events."""
        text = await asyncio.to_thread(self._send_sync, prompt)
        if text:
            yield {"type": "text", "text": text}
        yield {"type": "result", "text": text, "session_id": None, "usage": {}}
