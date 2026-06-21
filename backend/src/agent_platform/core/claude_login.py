"""Server-side ``claude`` login (clean re-login, no file copy).

Drives the real ``claude`` OAuth login over a PTY so the user can log in from
their browser and paste the code back into the app — exactly like logging in on a
new machine. The resulting full credentials are written by ``claude`` into
``CLAUDE_CONFIG_DIR`` (the persistent volume), which authenticates *every* engine
(including interactive), not just the inference-only ``setup-token``.

Flow:
  start()        -> spawns claude, answers the onboarding (theme + "subscription"),
                    returns the OAuth URL and waits at the "Paste code" prompt.
  submit_code()  -> sends the pasted code, waits for the credentials file to land.
"""

from __future__ import annotations

import logging
import os
import re
import time

import pexpect
import pyte

logger = logging.getLogger(__name__)

_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[=>]|\r")
_URL = re.compile(r"https://claude\.com/cai/oauth/authorize\?\S+")


class LoginError(RuntimeError):
    """Raised when the login flow cannot be driven."""


class ClaudeLogin:
    """A single in-progress ``claude`` browser login."""

    def __init__(self, binary: str = "claude", timeout_seconds: float = 150.0) -> None:
        self._binary = binary
        self._timeout = timeout_seconds
        self._child: pexpect.spawn | None = None
        self._raw = ""
        self._screen = pyte.Screen(4000, 50)
        self._stream = pyte.Stream(self._screen)
        self._creds_path = os.path.join(
            os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"),
            ".credentials.json",
        )

    def _read(self, duration: float) -> None:
        assert self._child is not None
        end = time.time() + duration
        while time.time() < end:
            try:
                data = self._child.read_nonblocking(size=65536, timeout=0.3)
            except pexpect.TIMEOUT:
                continue
            except pexpect.EOF:
                return
            if data:
                self._raw += data  # raw buffer holds the (contiguous) OAuth URL
                self._stream.feed(data)  # pyte renders the *current* screen state

    def _current_screen(self) -> str:
        return "\n".join(self._screen.display).lower()

    def _clean(self) -> str:
        return _ANSI.sub("", self._raw)

    def start(self) -> str:
        """Spawn claude and return the OAuth URL to open.

        Works whether claude is already signed in or not: if it lands on the main
        prompt (already authed via token/creds) we send ``/login`` to force a real
        re-login; if it's a fresh session we step through the onboarding. Either
        path ends at the OAuth URL.
        """
        # Very wide terminal so the long OAuth URL prints on a single line (no wrap).
        self._child = pexpect.spawn(
            self._binary, encoding="utf-8", dimensions=(50, 4000), timeout=self._timeout
        )
        deadline = time.time() + self._timeout
        login_sent = False
        while time.time() < deadline:
            self._read(1.5)
            url = _URL.search(self._clean())
            if url:
                return url.group(0)
            screen = self._current_screen()
            if "trust this folder" in screen or "safety check" in screen:
                self._child.send("\r")  # default = "Yes, I trust this folder"
                self._read(2.0)
            elif "text style" in screen or "choose the text" in screen:
                self._child.send("\r")  # accept default theme
                self._read(2.0)
            elif "login method" in screen:
                self._child.send("\r")  # default = Claude subscription
                self._read(2.0)
            elif not login_sent and ("for shortcuts" in screen or "for agents" in screen):
                # Already signed in → force a real re-login from the main prompt.
                self._child.send("/login")
                time.sleep(0.3)
                self._child.send("\r")
                login_sent = True
                self._read(2.0)
        last = self._current_screen().strip()[-600:]
        self.close()
        raise LoginError(f"timed out waiting for the login URL; last screen: {last!r}")

    def _creds_mtime(self) -> float:
        try:
            return os.path.getmtime(self._creds_path)
        except OSError:
            return 0.0

    def submit_code(self, code: str) -> bool:
        """Send the pasted OAuth code; return True once the login succeeds.

        Success = the credentials file is (re)written or the UI confirms login;
        failure = an 'invalid'/'error' message. (The creds file usually already
        exists, so we watch its mtime, not just its presence.)
        """
        if self._child is None:
            raise LoginError("login not started")
        before_mtime = self._creds_mtime()
        self._child.send(code.strip())
        time.sleep(0.3)
        self._child.send("\r")
        deadline = time.time() + 60
        while time.time() < deadline:
            self._read(1.0)
            recent = self._clean().lower()[-600:]
            if self._creds_mtime() > before_mtime or "login successful" in recent or "logged in" in recent:
                time.sleep(1.0)
                self.close()
                return True
            if "invalid" in recent or "error" in recent or "failed" in recent:
                self.close()
                return False
        self.close()
        return self._creds_mtime() > before_mtime

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
