"""API routes.

Implements the Phase 0 endpoints. Every handler returns the standard response
envelope and uses proper HTTP status codes. Business logic lives in the
:class:`SessionManager`; handlers only translate between HTTP and the manager.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from agent_platform import __version__
from agent_platform.api.dependencies import get_session_manager, require_api_key
from agent_platform.core.session_manager import SessionManager, SessionNotFoundError
from agent_platform.models.responses import ApiError, ApiSuccess

logger = logging.getLogger(__name__)
router = APIRouter()

ManagerDep = Annotated[SessionManager, Depends(get_session_manager)]
# Applied to every endpoint except /health to authenticate against the gateway key.
AuthDep = Depends(require_api_key)

# Maps SessionManager error codes to HTTP status codes.
_ERROR_STATUS = {
    "AGENT_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "BACKEND_TIMEOUT": status.HTTP_504_GATEWAY_TIMEOUT,
    "BACKEND_ERROR": status.HTTP_502_BAD_GATEWAY,
}


class CreateAgentRequest(BaseModel):
    """Body for creating an agent."""

    name: str = Field(min_length=1, max_length=100, description="Human-friendly agent name.")


class ChatRequest(BaseModel):
    """Body for sending a message to an agent."""

    agent_id: str = Field(min_length=1, description="Target agent id.")
    message: str = Field(min_length=1, description="The prompt to send to the agent.")
    mode: Literal["plan", "auto"] | None = Field(
        default=None,
        description="Per-message agent mode: 'plan' (propose only, no changes) or "
        "'auto' (full execution). Omit to use the server default.",
    )


# "plan" mode: restrict to read-only tools and prepend a planning instruction so
# the agent returns a clear plan and changes nothing (using the CLI's own
# --permission-mode plan instead awaits an interactive approval that our UI can't
# give). "auto" mode: full execution.
_PLAN_TOOLS = "Read Grep Glob WebFetch WebSearch"
_PLAN_INSTRUCTION = (
    "[PLAN MODE — do NOT make any changes: do not create or edit files and do not "
    "run commands. Reply ONLY with a short, numbered plan of what you would do.]\n\n"
)


def _resolve_mode(mode: str | None, message: str) -> tuple[str | None, str | None, str | None]:
    """Map a product mode to (permission_mode, allowed_tools, prompt_override)."""
    if mode == "plan":
        return None, _PLAN_TOOLS, _PLAN_INSTRUCTION + message
    if mode == "auto":
        return "bypassPermissions", None, None
    return None, None, None


def _error_response(code: str, message: str, http_status: int) -> JSONResponse:
    body = ApiError(error=message, code=code).model_dump()
    return JSONResponse(status_code=http_status, content=body)


@router.get("/health", tags=["system"])
def health(request: Request) -> ApiSuccess[dict[str, str]]:
    """Liveness probe. Used by Docker/Railway health checks.

    Also reports whether API auth is active, so a deployment's configuration can
    be verified without exposing the key.
    """
    auth = "enabled" if getattr(request.app.state, "gateway_api_key", None) else "disabled"
    return ApiSuccess(data={"service": "agent-platform", "version": __version__, "auth": auth})


@router.post("/agents", status_code=status.HTTP_201_CREATED, tags=["agents"], dependencies=[AuthDep])
def create_agent(body: CreateAgentRequest, manager: ManagerDep) -> ApiSuccess[dict[str, object]]:
    """Create a new agent (Claude Code session).

    Returns the created agent's summary including its generated ``id``.
    """
    agent_id = manager.create_session(body.name)
    return ApiSuccess(data=manager.get_session(agent_id))


@router.get("/agents", tags=["agents"], dependencies=[AuthDep])
def list_agents(manager: ManagerDep) -> ApiSuccess[dict[str, object]]:
    """List all active agents."""
    return ApiSuccess(data={"agents": manager.list_sessions()})


@router.get("/agents/{agent_id}/outputs", tags=["agents"], dependencies=[AuthDep])
def get_agent_outputs(agent_id: str, manager: ManagerDep) -> JSONResponse:
    """Return the accumulated outputs (interaction history) for an agent."""
    try:
        outputs = manager.get_outputs(agent_id)
    except SessionNotFoundError:
        return _error_response("AGENT_NOT_FOUND", f"No agent with id {agent_id!r}", status.HTTP_404_NOT_FOUND)
    body = ApiSuccess(data={"agent_id": agent_id, "outputs": outputs}).model_dump()
    return JSONResponse(status_code=status.HTTP_200_OK, content=body)


@router.post("/chat", tags=["chat"], dependencies=[AuthDep])
async def chat(body: ChatRequest, manager: ManagerDep) -> JSONResponse:
    """Send a message to an agent and return its response."""
    permission_mode, allowed_tools, prompt_override = _resolve_mode(body.mode, body.message)
    result = await manager.send_message(
        body.agent_id,
        body.message,
        permission_mode=permission_mode,
        allowed_tools=allowed_tools,
        prompt_override=prompt_override,
    )

    if result.get("status") == "success":
        body_out = ApiSuccess(
            data={
                "agent_id": result["agent_id"],
                "response": result["response"],
                "session_id": result["session_id"],
                "usage": result["usage"],
            }
        ).model_dump()
        return JSONResponse(status_code=status.HTTP_200_OK, content=body_out)

    code = str(result.get("code", "INTERNAL_ERROR"))
    http_status = _ERROR_STATUS.get(code, status.HTTP_500_INTERNAL_SERVER_ERROR)
    return _error_response(code, str(result.get("error", "Unknown error")), http_status)


@router.post("/chat/stream", tags=["chat"], dependencies=[AuthDep])
async def chat_stream(body: ChatRequest, manager: ManagerDep) -> StreamingResponse:
    """Stream an agent's progress live as newline-delimited JSON (NDJSON) events.

    Each line is a UI event: ``{"type": "text"|"tool"|"result"|"error", ...}``.
    Consume with fetch + a ReadableStream reader (EventSource can't send the
    API-key header).
    """
    permission_mode, allowed_tools, prompt_override = _resolve_mode(body.mode, body.message)

    async def event_stream() -> AsyncIterator[bytes]:
        async for event in manager.stream_message(
            body.agent_id,
            body.message,
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            prompt_override=prompt_override,
        ):
            yield (json.dumps(event) + "\n").encode("utf-8")

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
