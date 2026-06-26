"""Proof 2 — drive a REAL interactive `claude` (no -p, no SDK) and capture its
message through the MCP bus channel, WITHOUT ever parsing the terminal screen.

We spawn `claude` in a PTY, type a kickoff message like a human would, hit Enter,
then watch the bus file. When the agent calls `post_message`, our MCP server
records the clean content. The terminal output (Ink/ANSI) is never read.
"""

import json
import sys
import time
from pathlib import Path

import pexpect

POC = Path(__file__).parent
BUS_FILE = POC / "bus.jsonl"  # must match BUS_FILE in mcp-config.A.json
MCP_CONFIG = POC / "mcp-config.A.json"

KICKOFF = (
    "Use the post_message tool to send a message. Set content to a single clean "
    'sentence introducing yourself as "agent A". Set to="agentB". '
    "Do not print the message in the chat — only call the tool, then stop."
)


def bus_lines() -> list[dict]:
    if not BUS_FILE.exists():
        return []
    return [json.loads(line) for line in BUS_FILE.read_text().splitlines() if line.strip()]


def main() -> int:
    BUS_FILE.unlink(missing_ok=True)
    start_count = 0

    child = pexpect.spawn(
        "claude",
        [
            "--mcp-config", str(MCP_CONFIG),
            "--strict-mcp-config",
            "--allowedTools", "mcp__bus__post_message",
        ],
        encoding="utf-8",
        dimensions=(40, 120),
        timeout=180,
        cwd=str(POC),
    )
    # Mirror the TUI to a log for OUR debugging only — never parsed for the result.
    child.logfile_read = open(POC / "interactive_tui.log", "w", encoding="utf-8")

    print("[driver] spawned interactive claude, letting the TUI boot...", flush=True)
    time.sleep(8)  # let Ink render the input box

    print("[driver] typing kickoff message like a human...", flush=True)
    child.send(KICKOFF)
    time.sleep(1.0)  # let the paste settle before submitting
    child.send("\r")  # Enter

    print("[driver] waiting for the agent to emit via the bus channel...", flush=True)
    deadline = time.time() + 150
    while time.time() < deadline:
        msgs = bus_lines()
        if len(msgs) > start_count:
            print("\n[driver] ✅ message received through the channel (no screen scraping):", flush=True)
            print(json.dumps(msgs[-1], ensure_ascii=False, indent=2), flush=True)
            child.sendcontrol("c")
            time.sleep(0.5)
            child.close(force=True)
            return 0
        time.sleep(1.0)

    print("[driver] ❌ timeout — no message hit the bus", flush=True)
    child.close(force=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
