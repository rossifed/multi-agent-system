"""Live-agent orchestrator.

Runs one or more interactive ``claude`` agents attached to the bus and decides WHO
speaks WHEN. It watches the shared bus and, when a message is addressed to a managed
agent, WAKES that agent by typing a short nudge into its PTY — the agent then calls
``read_messages`` and replies via ``post_message``. The human (driven by the web UI)
is just another participant on the same bus.

Two concerns are kept separate and independently testable:
  - :func:`select_pending` — PURE dispatch logic (which messages need an agent woken).
  - :class:`AgentProcess` — the PTY runtime (spawn claude, drain its output, nudge it).

The PTY runtime carries the lesson from the ping-pong POC: an interactive agent's PTY
output MUST be drained continuously or the agent blocks on a full buffer.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Protocol, runtime_checkable

import pexpect

from agent_platform.bus import BusMessage, FileMessageStore, MessageBus
from agent_platform.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are {agent_id}, an assistant reachable on a shared message bus. RULES: To "
    "reply to anyone you MUST call the post_message tool with to=<their id>. To read "
    "incoming messages, call read_messages. NEVER write your reply in the chat — only "
    "use the tools. Be concise and helpful."
)

WAKE_PROMPT = "You have new messages. Call read_messages, then reply to each sender with post_message."


def select_pending(messages: list[BusMessage], managed: set[str], dispatched: set[str]) -> list[BusMessage]:
    """Return messages that should trigger waking a managed agent.

    A message qualifies when it is addressed to a managed agent, was not sent by a
    managed agent (we don't react to our own agents' output), and has not already
    been reacted to.

    Args:
        messages: The full bus history.
        managed: Ids of agents this orchestrator drives.
        dispatched: Ids of messages already reacted to.

    Returns:
        The qualifying messages, in order.
    """
    return [
        message
        for message in messages
        if message.id not in dispatched
        and message.sender not in managed
        and message.recipient in managed
    ]


@runtime_checkable
class Waker(Protocol):
    """Something that can be woken to take a turn (an agent PTY, or a test fake)."""

    def wake(self, text: str) -> None:
        """Deliver a nudge so the agent reads and responds."""
        ...

    def submit(self) -> None:
        """Re-submit (press Enter) in case a typed nudge was not sent."""
        ...


class Orchestrator:
    """Watches the bus and wakes managed agents when messages target them."""

    def __init__(self, bus: MessageBus, agents: dict[str, Waker]) -> None:
        """Initialize the orchestrator.

        Args:
            bus: The shared message bus.
            agents: Mapping of managed agent id -> its waker.
        """
        self._bus = bus
        self._agents = agents
        self._managed = set(agents)
        self._dispatched: set[str] = set()

    def seed(self) -> None:
        """Mark all pre-existing messages as handled so old history is not replayed."""
        for message in self._bus.history():
            self._dispatched.add(message.id)

    def tick(self, wait_timeout: float = 120.0, poll_interval: float = 0.5) -> str | None:
        """Process one pending message: wake its target agent and await the reply.

        Args:
            wait_timeout: Max seconds to wait for the agent to post a reply.
            poll_interval: Seconds between checks while waiting.

        Returns:
            The id of the agent woken, or ``None`` if nothing was pending.
        """
        pending = select_pending(self._bus.history(), self._managed, self._dispatched)
        if not pending:
            return None

        target = pending[0].recipient
        assert target is not None  # select_pending guarantees recipient in managed
        for message in pending:
            self._dispatched.add(message.id)

        before = len(self._bus.history())
        agent = self._agents[target]
        agent.wake(WAKE_PROMPT)
        if not self._wait_for_growth(before, wait_timeout, poll_interval):
            # The nudge may have been typed but not submitted — press Enter and retry.
            agent.submit()
            self._wait_for_growth(before, wait_timeout, poll_interval)
        return target

    def _wait_for_growth(self, before: int, timeout: float, poll_interval: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if len(self._bus.history()) > before:
                return True
            if poll_interval > 0:
                time.sleep(poll_interval)
            else:
                return len(self._bus.history()) > before
        return False

    def run(self, poll_interval: float = 0.5) -> None:  # pragma: no cover - infinite loop
        """Run forever: seed history, then dispatch pending messages as they arrive."""
        self.seed()
        logger.info("Orchestrator running", extra={"agents": sorted(self._managed)})
        while True:
            if self.tick() is None:
                time.sleep(poll_interval)


def write_agent_mcp_config(directory: Path, agent_id: str, bus_file: Path, conversation_id: str | None) -> Path:
    """Write the per-agent MCP config that attaches the bus server, return its path."""
    env = {"AGENT_ID": agent_id, "BUS_FILE": str(bus_file)}
    if conversation_id:
        env["CONVERSATION_ID"] = conversation_id
    config = {
        "mcpServers": {
            "bus": {
                # sys.executable = this venv's python, guaranteed to import agent_platform.
                "command": sys.executable,
                "args": ["-m", "agent_platform.bus.mcp_server"],
                "env": env,
            }
        }
    }
    path = directory / f"mcp-config.{agent_id}.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


class AgentProcess:  # pragma: no cover - PTY runtime, exercised in the live demo
    """An interactive ``claude`` agent in a PTY, attached to the bus.

    Continuously drains its PTY output (the lesson from the ping-pong POC: an
    undrained PTY blocks the agent on write).
    """

    def __init__(self, agent_id: str, config_path: Path) -> None:
        self._agent_id = agent_id
        self._child = pexpect.spawn(
            "claude",
            [
                "--mcp-config", str(config_path),
                "--strict-mcp-config",
                "--allowedTools", "mcp__bus__post_message", "mcp__bus__read_messages",
                "--append-system-prompt", SYSTEM_PROMPT.format(agent_id=agent_id),
            ],
            encoding="utf-8",
            dimensions=(50, 120),
            timeout=240,
        )
        self._stop = threading.Event()
        self._drainer = threading.Thread(target=self._drain, daemon=True)
        self._drainer.start()

    def _drain(self) -> None:
        while not self._stop.is_set():
            try:
                self._child.read_nonblocking(size=4096, timeout=1)
            except pexpect.TIMEOUT:
                continue
            except (pexpect.EOF, OSError):
                break

    def wake(self, text: str) -> None:
        self._child.send(text)
        time.sleep(1.5)  # let the paste settle before submitting
        self._child.send("\r")

    def submit(self) -> None:
        self._child.send("\r")

    def close(self) -> None:
        self._stop.set()
        time.sleep(1.2)
        try:
            self._child.sendcontrol("c")
            time.sleep(0.3)
            self._child.close(force=True)
        except Exception:  # best-effort teardown
            pass


def main() -> None:  # pragma: no cover - process entrypoint, run in the live demo
    """CLI: spawn a managed agent and run the orchestrator loop."""
    import argparse

    parser = argparse.ArgumentParser(description="Run a live claude agent on the bus.")
    parser.add_argument("--agent", default="agentA", help="Managed agent id.")
    parser.add_argument("--conversation", default=None, help="Optional conversation id.")
    args = parser.parse_args()

    settings = get_settings()
    bus_file = Path(settings.bus_file).resolve()
    bus_file.parent.mkdir(parents=True, exist_ok=True)
    bus = MessageBus(FileMessageStore(bus_file))

    config_path = write_agent_mcp_config(bus_file.parent, args.agent, bus_file, args.conversation)
    logger.info("Spawning agent %s (bus=%s)", args.agent, bus_file)
    agent = AgentProcess(args.agent, config_path)
    try:
        Orchestrator(bus, {args.agent: agent}).run()
    except KeyboardInterrupt:
        logger.info("Orchestrator stopped")
    finally:
        agent.close()


if __name__ == "__main__":  # pragma: no cover
    main()
