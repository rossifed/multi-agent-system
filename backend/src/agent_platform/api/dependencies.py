"""FastAPI dependencies.

Exposes the application's :class:`SessionManager` to route handlers. The manager
is stored on ``app.state`` (set by the application factory) so it can be easily
overridden in tests.
"""

from __future__ import annotations

from fastapi import Request

from agent_platform.core.session_manager import SessionManager


def get_session_manager(request: Request) -> SessionManager:
    """Return the application-wide :class:`SessionManager`.

    Args:
        request: The incoming request (provides access to ``app.state``).

    Returns:
        The configured session manager.
    """
    return request.app.state.session_manager
