"""MCP server exposing the bus tools to a Claude agent.

This is how an agent reaches the Python-owned channel: it CALLS a tool instead of
printing to the terminal, so the content arrives clean (a tool argument) and the
call is an unambiguous end-of-turn signal — and it works in every mode (interactive,
``-p``, SDK).

The tool handlers (:func:`post`, :func:`read`) hold the testable logic and delegate
to :class:`~agent_platform.bus.MessageBus`. :func:`create_server` only wires those
handlers to FastMCP; :func:`main` builds everything from the environment and runs the
stdio server (one process per agent, spawned by ``claude`` via ``--mcp-config``).

Environment (set per agent in the MCP config):
    AGENT_ID         -- this agent's participant id (the ``sender``).
    BUS_FILE         -- path to the shared JSONL bus file.
    CONVERSATION_ID  -- optional conversation grouping id.
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from agent_platform.bus import FileMessageStore, MessageBus


def post(
    bus: MessageBus,
    participant_id: str,
    conversation_id: str | None,
    content: str,
    to: str | None = None,
    message_type: str = "text",
) -> str:
    """Emit a message and return a short acknowledgement string."""
    message = bus.post(
        content=content,
        sender=participant_id,
        recipient=to,
        message_type=message_type,
        conversation_id=conversation_id,
    )
    return f"posted ({message.message_type})" + (f" to {to}" if to else "")


def read(bus: MessageBus, participant_id: str) -> list[dict]:
    """Return new messages addressed to ``participant_id`` as plain dicts."""
    return [message.model_dump(mode="json") for message in bus.read(participant_id)]


def create_server(bus: MessageBus, participant_id: str, conversation_id: str | None = None) -> FastMCP:
    """Build a FastMCP server whose tools are bound to ``bus`` and this agent."""
    server = FastMCP("bus")

    @server.tool()
    def post_message(content: str, to: str | None = None, message_type: str = "text") -> str:
        """Send a message to another participant.

        Use this instead of printing your answer.
          - content: your full message as plain text.
          - to: optional destination (another participant id, or a topic). Omit to
            let the system route it.
          - message_type: e.g. "text", "request", "result", "ack". Default "text".
        """
        return post(bus, participant_id, conversation_id, content, to, message_type)

    @server.tool()
    def read_messages() -> list[dict]:
        """Read new messages addressed to you that you have not read yet.

        Reading a message consumes it, so it is not returned again.
        """
        return read(bus, participant_id)

    return server


def main() -> None:  # pragma: no cover - process entrypoint, exercised at runtime
    """Build the server from the environment and run it over stdio."""
    bus = MessageBus(FileMessageStore(os.environ.get("BUS_FILE", "./data/bus.jsonl")))
    participant_id = os.environ.get("AGENT_ID", "unknown")
    conversation_id = os.environ.get("CONVERSATION_ID")
    create_server(bus, participant_id, conversation_id).run()


if __name__ == "__main__":  # pragma: no cover
    main()
