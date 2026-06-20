"""Probe: how does interactive `claude` (no -p) behave when driven from Python via a PTY?

Goal: empirically observe the raw I/O so we can build a reliable PoC. This is a
throwaway diagnostic — it spawns claude, captures the initial screen, sends one
message, captures the reply, then forcibly terminates. ANSI escapes are stripped
for readability in the printout.
"""

from __future__ import annotations

import re
import sys
import time

import pexpect

ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[=>]|\r")


def clean(text: str) -> str:
    return ANSI.sub("", text)


def main() -> None:
    print(">>> spawning `claude` under a PTY ...", flush=True)
    child = pexpect.spawn(
        "claude",
        encoding="utf-8",
        dimensions=(40, 120),
        timeout=20,
    )
    captured: list[str] = []
    try:
        # 1) Let the initial UI render.
        time.sleep(6)
        try:
            initial = child.read_nonblocking(size=65536, timeout=2)
        except Exception:
            initial = ""
        captured.append("=== INITIAL SCREEN ===\n" + clean(initial))

        # 2) Send a trivial prompt.
        print(">>> sending a prompt ...", flush=True)
        child.send("Reply with exactly one word: PONG")
        time.sleep(1)
        child.send("\r")

        # 3) Drain output for a while to catch the reply.
        deadline = time.time() + 25
        buf = ""
        while time.time() < deadline:
            try:
                buf += child.read_nonblocking(size=65536, timeout=2)
            except pexpect.TIMEOUT:
                continue
            except pexpect.EOF:
                break
        captured.append("=== AFTER PROMPT ===\n" + clean(buf))
    finally:
        # 4) Always terminate the child.
        try:
            child.sendcontrol("c")
            time.sleep(0.3)
            child.sendcontrol("c")
            child.terminate(force=True)
        except Exception:
            pass

    out = "\n\n".join(captured)
    # Trim noise: collapse runs of blank lines.
    out = re.sub(r"\n{3,}", "\n\n", out)
    print(out[-6000:], flush=True)
    print("\n>>> probe done.", flush=True)


if __name__ == "__main__":
    sys.exit(main())
