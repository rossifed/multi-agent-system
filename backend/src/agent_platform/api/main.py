"""FastAPI application factory.

Wires together configuration, logging, the session manager, CORS, routes, and
global exception handlers. Use :func:`create_app` to build an instance; the
module-level :data:`app` is the ASGI entrypoint for uvicorn.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent_platform import __version__
from agent_platform.api.bus_routes import router as bus_router
from agent_platform.api.routes import router
from agent_platform.bus import FileMessageStore, MessageBus
from agent_platform.config import Settings, get_settings
from agent_platform.core.backends import build_backend
from agent_platform.core.session_manager import SessionManager
from agent_platform.logging_config import configure_logging
from agent_platform.models.responses import ApiError

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    session_manager: SessionManager | None = None,
    bus: MessageBus | None = None,
) -> FastAPI:
    """Build and configure the FastAPI application.

    Args:
        settings: Optional settings override (defaults to :func:`get_settings`).
        session_manager: Optional pre-built session manager. When omitted, one is
            constructed from ``settings`` during startup. Injection is used by tests.
        bus: Optional pre-built message bus. When omitted, a file-backed bus is built
            from ``settings.bus_file``. Injection is used by tests.

    Returns:
        A configured :class:`FastAPI` instance.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level, json_format=settings.log_json)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if not hasattr(application.state, "session_manager"):
            backend = build_backend(settings)
            application.state.session_manager = SessionManager(backend, settings.session_store_path)
        logger.info("Agent platform started", extra={"version": __version__, "backend": settings.backend})
        yield
        logger.info("Agent platform shutting down")

    app = FastAPI(
        title="Agent Platform",
        version=__version__,
        description="Phase 0 - Claude Code session gateway.",
        lifespan=lifespan,
    )

    # Injected manager is available immediately (before lifespan), which tests rely on.
    if session_manager is not None:
        app.state.session_manager = session_manager

    # The bus is cheap (just a file path) so it is built eagerly here rather than in
    # lifespan; an injected bus (tests) takes precedence.
    app.state.bus = bus or MessageBus(FileMessageStore(settings.bus_file))
    app.state.bus_stream_poll_seconds = settings.bus_stream_poll_seconds

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_exception_handlers(app)
    app.include_router(router)
    app.include_router(bus_router)
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers that emit the standard error envelope (no stack traces leak)."""

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ApiError(error=str(exc.errors()), code="VALIDATION_ERROR").model_dump(),
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ApiError(error="Internal server error", code="INTERNAL_ERROR").model_dump(),
        )


app = create_app()
