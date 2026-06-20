"""Integration tests for the FastAPI gateway (mock-backed)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from agent_platform.api.main import create_app
from agent_platform.config import Settings
from agent_platform.core.backends import MockBackend
from agent_platform.core.session_manager import SessionManager


@pytest.fixture
def authed_client() -> Iterator[TestClient]:
    """A TestClient whose app requires the gateway API key 'secret'."""
    settings = Settings(backend="mock", gateway_api_key="secret")
    manager = SessionManager(MockBackend(reply="echo"), None)
    app = create_app(settings=settings, session_manager=manager)
    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["data"]["service"] == "agent-platform"


def test_create_agent(client: TestClient) -> None:
    response = client.post("/agents", json={"name": "architect"})
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["name"] == "architect"
    assert data["status"] == "created"
    assert data["id"]


def test_create_agent_validation_error(client: TestClient) -> None:
    response = client.post("/agents", json={"name": ""})
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_list_agents(client: TestClient) -> None:
    client.post("/agents", json={"name": "a"})
    client.post("/agents", json={"name": "b"})
    response = client.get("/agents")
    assert response.status_code == 200
    assert len(response.json()["data"]["agents"]) == 2


def test_chat_success(client: TestClient) -> None:
    agent_id = client.post("/agents", json={"name": "dev"}).json()["data"]["id"]
    response = client.post("/chat", json={"agent_id": agent_id, "message": "Hello!"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["response"] == "echo: Hello!"
    assert data["session_id"]


def test_chat_unknown_agent_returns_404(client: TestClient) -> None:
    response = client.post("/chat", json={"agent_id": "ghost", "message": "hi"})
    assert response.status_code == 404
    assert response.json()["code"] == "AGENT_NOT_FOUND"


def test_chat_validation_error(client: TestClient) -> None:
    response = client.post("/chat", json={"agent_id": "x"})
    assert response.status_code == 400


def test_get_outputs(client: TestClient) -> None:
    agent_id = client.post("/agents", json={"name": "dev"}).json()["data"]["id"]
    client.post("/chat", json={"agent_id": agent_id, "message": "Hello!"})
    response = client.get(f"/agents/{agent_id}/outputs")
    assert response.status_code == 200
    outputs = response.json()["data"]["outputs"]
    assert len(outputs) == 2


def test_get_outputs_unknown_agent_returns_404(client: TestClient) -> None:
    response = client.get("/agents/ghost/outputs")
    assert response.status_code == 404
    assert response.json()["code"] == "AGENT_NOT_FOUND"


# --- API authentication ---


def test_health_is_open_without_key(authed_client: TestClient) -> None:
    assert authed_client.get("/health").status_code == 200


def test_protected_route_rejects_missing_key(authed_client: TestClient) -> None:
    response = authed_client.get("/agents")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_protected_route_rejects_wrong_key(authed_client: TestClient) -> None:
    response = authed_client.get("/agents", headers={"X-API-Key": "nope"})
    assert response.status_code == 401


def test_protected_route_accepts_x_api_key(authed_client: TestClient) -> None:
    response = authed_client.get("/agents", headers={"X-API-Key": "secret"})
    assert response.status_code == 200


def test_protected_route_accepts_bearer_token(authed_client: TestClient) -> None:
    response = authed_client.get("/agents", headers={"Authorization": "Bearer secret"})
    assert response.status_code == 200
