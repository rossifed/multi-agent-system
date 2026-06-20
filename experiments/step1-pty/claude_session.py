"""Step 1 PoC: drive the REAL interactive `claude` (no -p) from Python.

This is the thing the web terminal could NOT give us: *our own code* sits in the
middle of the conversation. We spawn `claude` in a pseudo-terminal (pexpect),
feed its byte stream into a terminal emulator (pyte) so we can read the rendered
screen cleanly, and expose a simple `send(message) -> reply` API.

It uses the interactive session (subscription auth, same as a local terminal),
NOT `claude -p`. The output is screen-scraped from a TUI, so it is inherently a
bit heuristic — that fragility is exactly why `-p`/stream-json is the better
primitive for the real product. This PoC only proves: *our code can hold a live,
multi-turn Claude session and wrap a layer around it.*
"""

from __future__ import annotations

import time

import pexpect
import pyte


class ClaudeSession:
    """A live interactive `claude` session driven programmatically."""

    def __init__(self, cwd: str | None = None, cols: int = 120, rows: int = 50) -> None:
        self._cwd = cwd
        self._cols = cols
        self._rows = rows
        self._child: pexpect.spawn | None = None
        self._screen = pyte.Screen(cols, rows)
        self._stream = pyte.Stream(self._screen)

    # --- lifecycle -------------------------------------------------------
    def start(self, settle_secs: float = 8.0) -> None:
        """Launch claude and wait for the initial UI to settle."""
        self._child = pexpect.spawn(
            "claude",
            cwd=self._cwd,
            encoding="utf-8",
            dimensions=(self._rows, self._cols),
            timeout=30,
        )
        self._wait_until_stable(min_secs=settle_secs, stable_secs=2.0, timeout=30)

    def close(self) -> None:
        if self._child is None:
            return
        try:
            self._child.sendcontrol("c")
            time.sleep(0.2)
            self._child.sendcontrol("c")
            self._child.terminate(force=True)
        except Exception:
            pass
        self._child = None

    def __enter__(self) -> "ClaudeSession":
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # --- interaction -----------------------------------------------------
    def send(self, message: str, stable_secs: float = 3.0, timeout: float = 90.0) -> str:
        """Send a message, wait for the reply to finish, return claude's answer."""
        assert self._child is not None, "session not started"
        before = set(self._assistant_lines())

        self._child.send(message)
        time.sleep(0.4)
        self._child.send("\r")

        self._wait_until_stable(min_secs=2.0, stable_secs=stable_secs, timeout=timeout)

        after = self._assistant_lines()
        # Return only the lines that appeared since this turn started.
        fresh = [ln for ln in after if ln not in before]
        return "\n".join(fresh).strip() or "\n".join(after[-3:]).strip()

    # --- internals -------------------------------------------------------
    def _pump(self, duration: float) -> bool:
        """Read available bytes for up to `duration`s into the emulator. Returns True if any read."""
        assert self._child is not None
        got = False
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
                got = True
        return got

    def _wait_until_stable(self, min_secs: float, stable_secs: float, timeout: float) -> None:
        """Pump output until the rendered screen stops changing for `stable_secs`."""
        start = time.time()
        self._pump(min_secs)
        last = self._render()
        last_change = time.time()
        while time.time() - start < timeout:
            self._pump(0.5)
            now = self._render()
            if now != last:
                last = now
                last_change = time.time()
            elif time.time() - last_change >= stable_secs:
                return

    def _render(self) -> str:
        return "\n".join(self._screen.display)

    def _assistant_lines(self) -> list[str]:
        """Extract claude's answer lines (marked with a bullet) from the screen."""
        lines = []
        for raw in self._screen.display:
            text = raw.rstrip()
            stripped = text.lstrip()
            if stripped.startswith("●"):
                cleaned = stripped.lstrip("●").strip()
                if cleaned:
                    lines.append(cleaned)
        return lines
