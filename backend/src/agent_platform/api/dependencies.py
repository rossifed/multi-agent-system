"""FastAPI dependencies.

Exposes the application's :class:`SessionManager` to route handlers and the API
authentication guard. Shared state lives on ``app.state`` (set by the application
factory) so it can be easily overridden in tests.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request, status

from agent_platform.core.session_manager import SessionManager

logger = logging.getLogger(__name__)


def get_session_manager(request: Request) -> SessionManager:
    """Return the application-wide :class:`SessionManager`.

    Args:
        request: The incoming request (provides access to ``app.state``).

    Returns:
        The configured session manager.
    """
    return request.app.state.session_manager


def require_api_key(request: Request) -> None:
    """Authenticate a request against the configured gateway API key.

    The key may be supplied as ``Authorization: Bearer <key>`` or ``X-API-Key:
    <key>``. When no key is configured the request is allowed (local dev), but a
    warning is logged so an unauthenticated public deployment is hard to miss.

    Args:
        request: The incoming request.

    Raises:
        HTTPException: 401 if a key is configured but missing/incorrect.
    """
    expected: str | None = getattr(request.app.state, "gateway_api_key", None)
    if not expected:
        logger.warning("API auth is DISABLED (no gateway_api_key set) — do not expose publicly")
        return

    provided = request.headers.get("x-api-key")
    if not provided:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            provided = auth[7:].strip()

    if provided != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
