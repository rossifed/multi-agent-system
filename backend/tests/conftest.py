"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_platform.api.main import create_app
from agent_platform.config import Settings
from agent_platform.core.backends import MockBackend
from agent_platform.core.session_manager import SessionManager


@pytest.fixture
def anyio_backend() -> str:
    """Run anyio-marked async tests on asyncio."""
    return "asyncio"


@pytest.fixture
def mock_backend() -> MockBackend:
    """A fresh recording mock backend."""
    return MockBackend(reply="echo")


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    """A temp path for the JSON session store."""
    return tmp_path / "sessions.json"


@pytest.fixture
def manager(mock_backend: MockBackend, store_path: Path) -> SessionManager:
    """A SessionManager backed by the mock backend and a temp store."""
    return SessionManager(mock_backend, store_path)


@pytest.fixture
def client(manager: SessionManager) -> Iterator[TestClient]:
    """A TestClient with the mock-backed manager injected."""
    settings = Settings(backend="mock", cors_origins=["http://localhost:3000"])
    app = create_app(settings=settings, session_manager=manager)
    with TestClient(app) as test_client:
        yield test_client
