"""Bus API routes.

Lets a HUMAN participate on the same bus as the agents — the human is just another
participant that posts and reads. The web UI uses these endpoints to:
  - POST /bus/post     -> send a message (human plays "agent B").
  - GET  /bus/history  -> the whole conversation (transparency, observer view).
  - GET  /bus/stream   -> Server-Sent Events pushing new messages live.

The SSE stream is server-side polling of the shared bus file (the file is also
written by the agents' MCP server processes), pushed to the browser as a clean
event stream so the client never polls.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent_platform.api.dependencies import get_bus
from agent_platform.bus import BusMessage, MessageBus
from agent_platform.models.responses import ApiSuccess

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bus", tags=["bus"])

BusDep = Annotated[MessageBus, Depends(get_bus)]


class PostMessageRequest(BaseModel):
    """Body for a human (or any caller) posting a message to the bus."""

    content: str = Field(min_length=1, description="The message body as plain text.")
    sender: str = Field(default="human", min_length=1, description="Participant id of the sender.")
    recipient: str | None = Field(default=None, description="Destination id or topic; null lets the router decide.")
    message_type: str = Field(default="text", min_length=1, description="Kind: text/request/result/ack/...")
    conversation_id: str | None = Field(default=None, description="Optional conversation grouping id.")


def _sse_format(message: BusMessage) -> str:
    """Encode a message as a single Server-Sent Event frame."""
    return f"data: {message.model_dump_json()}\n\n"


async def _stream_events(
    bus: MessageBus,
    is_disconnected: Callable[[], Awaitable[bool]],
    conversation_id: str | None = None,
    poll_interval: float = 0.5,
    max_polls: int | None = None,
) -> AsyncIterator[str]:
    """Yield SSE frames for new bus messages until the client disconnects.

    Args:
        bus: The message bus to observe.
        is_disconnected: Awaitable returning True when the client has gone away.
        conversation_id: Restrict the stream to one conversation when given.
        poll_interval: Seconds between polls of the bus.
        max_polls: Stop after this many polls (testing hook; ``None`` = run forever).

    Yields:
        SSE-formatted strings, one per new message.
    """
    sent = 0
    polls = 0
    while True:
        if await is_disconnected():
            break
        messages = bus.history(conversation_id)
        for message in messages[sent:]:
            yield _sse_format(message)
        sent = len(messages)
        polls += 1
        if max_polls is not None and polls >= max_polls:
            break
        await asyncio.sleep(poll_interval)


@router.post("/post")
def post_message(body: PostMessageRequest, bus: BusDep) -> ApiSuccess[dict[str, object]]:
    """Post a message onto the bus and return the stored envelope."""
    message = bus.post(
        content=body.content,
        sender=body.sender,
        recipient=body.recipient,
        message_type=body.message_type,
        conversation_id=body.conversation_id,
    )
    return ApiSuccess(data=message.model_dump(mode="json"))


@router.get("/history")
def history(bus: BusDep, conversation_id: str | None = None) -> ApiSuccess[dict[str, object]]:
    """Return the full conversation (observer view, never consumes)."""
    messages = [message.model_dump(mode="json") for message in bus.history(conversation_id)]
    return ApiSuccess(data={"messages": messages, "count": len(messages)})


@router.get("/stream", status_code=status.HTTP_200_OK)
def stream(request: Request, bus: BusDep, conversation_id: str | None = None) -> StreamingResponse:
    """Stream new bus messages to the browser as Server-Sent Events."""
    poll_interval = request.app.state.bus_stream_poll_seconds
    generator = _stream_events(bus, request.is_disconnected, conversation_id, poll_interval)
    return StreamingResponse(generator, media_type="text/event-stream")
