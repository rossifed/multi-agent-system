"""FastAPI dependencies.

Exposes the application's :class:`SessionManager` and :class:`MessageBus` to route
handlers. Both are stored on ``app.state`` (set by the application factory) so they
can be easily overridden in tests.
"""

from __future__ import annotations

from fastapi import Request

from agent_platform.bus import MessageBus
from agent_platform.core.session_manager import SessionManager


def get_session_manager(request: Request) -> SessionManager:
    """Return the application-wide :class:`SessionManager`.

    Args:
        request: The incoming request (provides access to ``app.state``).

    Returns:
        The configured session manager.
    """
    return request.app.state.session_manager


def get_bus(request: Request) -> MessageBus:
    """Return the application-wide :class:`MessageBus`.

    Args:
        request: The incoming request (provides access to ``app.state``).

    Returns:
        The configured message bus.
    """
    return request.app.state.bus
