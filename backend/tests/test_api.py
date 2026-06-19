"""Integration tests for the FastAPI gateway (mock-backed)."""

from __future__ import annotations

from fastapi.testclient import TestClient


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
