"""The agent-facing TOOL `post_message` — exposed to claude via MCP.

Decoupling principle: the agent only knows the tool SIGNATURE. It has no idea
where the message goes or how it is handled. Everything behind `deliver()` is
swappable — log now, message bus / API / pub-sub topic later — and the agent
never changes.

  agent  --calls-->  post_message(content, to?, message_type?)   [the contract]
                            |
                            v
                       deliver(message)                           [the swappable seam]
                            |
            log / bus / API / topic / ...                         [implementation, hidden]

Note on `to`: it is a generic DESTINATION label, NOT necessarily an agent. The
routing strategy is a Python concern, not the agent's:
  - direct addressing  -> `to` = an agent id
  - event / pub-sub     -> `to` = a topic
  - router-decided      -> `to` = None (the layer below decides where it goes)
So the envelope stays strategy-agnostic and will evolve.
"""

import json
import os
import time
import uuid
from pathlib import Path

from mcp.server.fastmcp import FastMCP

AGENT_ID = os.environ.get("AGENT_ID", "unknown")
CONVERSATION_ID = os.environ.get("CONVERSATION_ID")  # set by the orchestrator; may be None
SINK_FILE = Path(os.environ.get("BUS_FILE", Path(__file__).parent / "bus.jsonl"))

mcp = FastMCP("bus")


def deliver(message: dict) -> None:
    """THE SEAM (write side). Swap for a bus push / API call / topic publish later.

    First step (as agreed): just log the message so we can validate the format.
    The tool above stays identical regardless of what this does.
    """
    with SINK_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(message, ensure_ascii=False) + "\n")


def _seen_path() -> Path:
    return SINK_FILE.parent / f"{AGENT_ID}.seen"


def _load_seen() -> set[str]:
    path = _seen_path()
    return set(path.read_text().split()) if path.exists() else set()


def _save_seen(seen: set[str]) -> None:
    _seen_path().write_text("\n".join(sorted(seen)))


def fetch(recipient: str) -> list[dict]:
    """THE SEAM (read side). Same store now; could become a bus/topic poll later.

    Returns messages addressed to `recipient` (or broadcast) that this agent has
    not consumed yet, then marks them as seen so each is delivered once.
    """
    if not SINK_FILE.exists():
        return []
    seen = _load_seen()
    new_messages: list[dict] = []
    for line in SINK_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        msg = json.loads(line)
        if msg["from"] == recipient:  # never read your own messages
            continue
        if msg["to"] not in (recipient, None, "all"):  # not addressed to me
            continue
        if msg["id"] in seen:  # already consumed
            continue
        new_messages.append(msg)
        seen.add(msg["id"])
    _save_seen(seen)
    return new_messages


@mcp.tool()
def post_message(content: str, to: str | None = None, message_type: str = "text") -> str:
    """Send a message to another participant.

    Use this instead of printing your answer.
      - content: your full message as plain text.
      - to: optional destination (another agent id, or a topic). Omit to let the
        system route it.
      - message_type: e.g. "text", "request", "result", "ack". Default "text".
    """
    message = {
        "id": str(uuid.uuid4()),
        "ts": time.time(),
        "conversation_id": CONVERSATION_ID,
        "type": message_type,
        "from": AGENT_ID,
        "to": to,
        "content": content,
    }
    deliver(message)
    return f"posted ({message['type']})" + (f" to {to}" if to else "")


@mcp.tool()
def read_messages() -> list[dict]:
    """Read new messages addressed to you that you have not read yet.

    Returns a list of message envelopes (each with from/type/content). Reading a
    message consumes it, so it will not be returned again.
    """
    return fetch(AGENT_ID)


if __name__ == "__main__":
    mcp.run()
