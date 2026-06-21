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
        self._backup_path = self._creds_path + ".pre-login.bak"

    def _stash_existing_creds(self) -> None:
        """Move any existing (e.g. inference-only) credentials aside so the login
        flow actually triggers instead of claude assuming it's already signed in."""
        if os.path.exists(self._creds_path):
            os.replace(self._creds_path, self._backup_path)

    def _finalize_creds(self, success: bool) -> None:
        """Drop the backup on success; restore it if the login didn't complete."""
        if not os.path.exists(self._backup_path):
            return
        if success and os.path.exists(self._creds_path):
            os.remove(self._backup_path)
        elif not os.path.exists(self._creds_path):
            os.replace(self._backup_path, self._creds_path)

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
        """Spawn claude, clear onboarding, and return the OAuth URL to open."""
        # Force a fresh login by hiding any inference token so claude prompts to log in.
        env = dict(os.environ)
        env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
        env.pop("ANTHROPIC_API_KEY", None)
        self._stash_existing_creds()  # so the login flow actually triggers
        # Very wide terminal so the long OAuth URL is printed on a single line
        # (no wrap), letting us capture it whole from the raw stream.
        self._child = pexpect.spawn(
            self._binary, env=env, encoding="utf-8", dimensions=(50, 4000), timeout=self._timeout
        )
        deadline = time.time() + self._timeout
        while time.time() < deadline:
            self._read(1.5)
            # The URL is captured from the raw (contiguous) buffer; navigation
            # decisions use the *current* rendered screen so we don't re-answer a
            # screen we already passed.
            url = _URL.search(self._clean())
            if url:
                return url.group(0)
            screen = self._current_screen()
            if "text style" in screen or "choose the text" in screen:
                self._child.send("\r")  # accept default theme
                self._read(2.0)
            elif "select login method" in screen:
                self._child.send("\r")  # default = Claude subscription
                self._read(2.0)
        self.close()
        self._finalize_creds(success=False)  # restore prior creds
        raise LoginError("timed out waiting for the login URL")

    def submit_code(self, code: str) -> bool:
        """Send the pasted OAuth code; return True once credentials are written."""
        if self._child is None:
            raise LoginError("login not started")
        creds = self._creds_path
        self._child.send(code.strip())
        time.sleep(0.3)
        self._child.send("\r")
        deadline = time.time() + 45
        while time.time() < deadline:
            self._read(1.0)
            if os.path.exists(creds):
                time.sleep(1.0)  # let the file finish writing
                self.close()
                self._finalize_creds(success=True)
                return True
            if "invalid" in self._clean().lower()[-400:]:
                self.close()
                self._finalize_creds(success=False)
                return False
        self.close()
        ok = os.path.exists(creds)
        self._finalize_creds(success=ok)
        return ok

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
