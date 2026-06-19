# Agent Platform — Backend (Phase 0)

FastAPI gateway that manages **Claude Code sessions** ("agents") and routes
messages to them. Each agent is driven through the local `claude` CLI in headless
JSON mode, authenticated via the host's **Claude subscription (Max)** — it does
**not** require an API key and does **not** consume API credits.

## Layout

```
backend/
├─ src/agent_platform/
│  ├─ config.py            # env-driven settings (no hardcoded values)
│  ├─ logging_config.py    # human + JSON structured logging
│  ├─ models/              # Agent, Interaction, API envelopes
│  ├─ core/
│  │  ├─ backends.py       # ClaudeBackend protocol, CLI + Mock backends
│  │  └─ session_manager.py
│  └─ api/                 # FastAPI app factory, routes, dependencies
└─ tests/                  # unit + integration tests
```

## Setup

```bash
uv venv --python 3.11
uv pip install -e ".[dev]"
cp .env.example .env        # adjust if needed; defaults work out of the box
```

The `claude` CLI must be installed and logged in to a Claude subscription
(`claude` once interactively, or `claude setup-token`).

## Run

```bash
uv run uvicorn agent_platform.api.main:app --reload --port 8000
# OpenAPI docs: http://localhost:8000/docs
```

Set `AGENT_BACKEND=mock` to run without invoking Claude (canned responses).

## Endpoints

| Method | Path                         | Purpose                          |
|--------|------------------------------|----------------------------------|
| GET    | `/health`                    | Liveness probe                   |
| POST   | `/agents`                    | Create an agent (Claude session) |
| GET    | `/agents`                    | List agents                      |
| POST   | `/chat`                      | Send a message to an agent       |
| GET    | `/agents/{agent_id}/outputs` | Get an agent's interaction history |

All responses use the standard envelope:

```json
{ "status": "success", "data": { ... }, "timestamp": "..." }
{ "status": "error", "error": "...", "code": "...", "timestamp": "..." }
```

## Test, lint, type-check

```bash
uv run pytest                 # runs with coverage, fails under 80%
uv run ruff check . && uv run ruff format --check .
uv run pyright
```
