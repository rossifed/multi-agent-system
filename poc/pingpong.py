"""Ping-pong A<->B — two REAL interactive `claude` agents talking through the
Python-owned MCP channel, with a Python orchestrator handling turn-taking.

Design:
  - MCP bus  = WHAT is said   (post_message / read_messages, shared bus.jsonl).
  - Orchestrator = WHO speaks WHEN: it watches the bus and "wakes" the recipient
    agent by typing a short nudge into its PTY. No terminal screen is ever parsed;
    the conversation is read entirely from the bus file.
"""

import json
import sys
import threading
import time
import uuid
from pathlib import Path

import pexpect

POC = Path(__file__).parent
BUS = POC / "bus.jsonl"
CONVERSATION = "pingpong-" + uuid.uuid4().hex[:8]
EXCHANGES = 3  # how many replies after the kickoff

SYSTEM_PROMPT = (
    "You are {me}, one of two agents in a short ping-pong demo with {other}. "
    "RULES: To say anything to {other} you MUST call the post_message tool with "
    "to='{other}'. To receive, call read_messages. NEVER write your message in the "
    "chat — only use the tools. Keep every message to ONE short friendly sentence."
)


def make_config(agent_id: str) -> Path:
    cfg = {
        "mcpServers": {
            "bus": {
                "command": "uv",
                "args": ["run", "--with", "mcp", "--no-project", "python", str(POC / "bus_server.py")],
                "env": {"AGENT_ID": agent_id, "BUS_FILE": str(BUS), "CONVERSATION_ID": CONVERSATION},
            }
        }
    }
    path = POC / f"mcp-config.{agent_id}.gen.json"
    path.write_text(json.dumps(cfg, indent=2))
    return path


def spawn(agent_id: str, other: str) -> pexpect.spawn:
    config = make_config(agent_id)
    child = pexpect.spawn(
        "claude",
        [
            "--mcp-config", str(config),
            "--strict-mcp-config",
            "--allowedTools", "mcp__bus__post_message", "mcp__bus__read_messages",
            "--append-system-prompt", SYSTEM_PROMPT.format(me=agent_id, other=other),
        ],
        encoding="utf-8",
        dimensions=(50, 120),
        timeout=240,
        cwd=str(POC),
    )
    return child


def drain(child: pexpect.spawn, agent_id: str, stop: threading.Event) -> None:
    """CRITICAL: continuously read & discard each agent's PTY output so its buffer
    never fills (an undrained PTY blocks the child on write, freezing the agent).
    We don't need the screen content — it comes from the bus — but we MUST drain it.
    A copy is logged for debugging only; it is never parsed for the conversation.
    """
    with open(POC / f"{agent_id}.tui.log", "w", encoding="utf-8", buffering=1) as log:
        while not stop.is_set():
            try:
                data = child.read_nonblocking(size=4096, timeout=1)
                if data:
                    log.write(data)
            except pexpect.TIMEOUT:
                continue
            except (pexpect.EOF, OSError):
                break


def bus_lines() -> list[dict]:
    if not BUS.exists():
        return []
    return [json.loads(line) for line in BUS.read_text(encoding="utf-8").splitlines() if line.strip()]


def submit(child: pexpect.spawn) -> None:
    child.send("\r")


def nudge(child: pexpect.spawn, text: str) -> None:
    child.send(text)
    time.sleep(1.5)  # let the paste settle before submitting
    submit(child)


def wait_for_new_message(previous_count: int, timeout: int = 80) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(bus_lines()) > previous_count:
            return True
        time.sleep(1.0)
    return False


def nudge_with_retry(child: pexpect.spawn, text: str, previous_count: int) -> bool:
    """Wake an agent and wait; if nothing came, the text was likely typed but not
    submitted — press Enter again once before giving up."""
    nudge(child, text)
    if wait_for_new_message(previous_count, timeout=80):
        return True
    print("[orch]   …no response, re-submitting (Enter) once…", flush=True)
    submit(child)
    return wait_for_new_message(previous_count, timeout=80)


def main() -> int:
    BUS.unlink(missing_ok=True)
    for stale in POC.glob("*.seen"):
        stale.unlink()

    children = {"agentA": spawn("agentA", "agentB"), "agentB": spawn("agentB", "agentA")}
    stop = threading.Event()
    drainers = [threading.Thread(target=drain, args=(child, aid, stop), daemon=True) for aid, child in children.items()]
    for thread in drainers:
        thread.start()
    print(f"[orch] conversation={CONVERSATION} — booting two interactive agents (PTY drainers on)...", flush=True)
    time.sleep(10)

    # Kickoff: A starts the conversation.
    count = len(bus_lines())
    print("[orch] waking agentA to start...", flush=True)
    if not nudge_with_retry(children["agentA"], "Start the conversation: greet agentB and ask one question. Use post_message to='agentB'.", count):
        print("[orch] ❌ kickoff timed out", flush=True)
        return _shutdown(children, stop, 1)
    last = bus_lines()[-1]
    print(f"[orch] agentA → agentB: {last['content']}", flush=True)

    # Turn loop: the recipient of the last message speaks next.
    for turn in range(EXCHANGES):
        recipient = bus_lines()[-1]["to"]
        if recipient not in children:
            print(f"[orch] last message addressed to '{recipient}' (not an agent) — stopping.", flush=True)
            break
        count = len(bus_lines())
        print(f"[orch] waking {recipient} (turn {turn + 1}/{EXCHANGES})...", flush=True)
        if not nudge_with_retry(children[recipient], "Your turn: call read_messages, then reply to the sender with post_message. One short sentence.", count):
            print(f"[orch] ❌ {recipient} timed out on turn {turn + 1}", flush=True)
            break
        last = bus_lines()[-1]
        print(f"[orch] {last['from']} → {last['to']}: {last['content']}", flush=True)

    print("\n[orch] ===== full conversation (read from the bus, not the screen) =====", flush=True)
    for msg in bus_lines():
        print(f"  [{msg['type']}] {msg['from']} → {msg['to']}: {msg['content']}", flush=True)
    return _shutdown(children, stop, 0)


def _shutdown(children: dict, stop: threading.Event, code: int) -> int:
    stop.set()  # tell the drainer threads to exit
    time.sleep(1.2)
    for child in children.values():
        try:
            child.sendcontrol("c")
            time.sleep(0.3)
            child.close(force=True)
        except Exception:
            pass
    return code


if __name__ == "__main__":
    sys.exit(main())
