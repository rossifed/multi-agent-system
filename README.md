# Multi-Agent System — Phase 0 (Foundation)

A platform where autonomous agents orchestrate software-development tasks. **Phase 0**
delivers the foundation: a containerized FastAPI gateway that creates and manages
**Claude Code sessions** ("agents") and a simple web UI to talk to them.

> **Billing model — important.** Agents are driven through the local `claude` CLI in
> headless mode, authenticated with a **Claude subscription (Max)** token. This path
> uses your subscription quota and **does not consume API credits**. Using the
> Anthropic API or the Agent SDK instead *would* bill API credits — so Phase 0
> deliberately avoids them. (Verified against the official Claude Code docs.)

## Architecture

```
┌──────────────┐      HTTP/JSON       ┌───────────────────────────────┐
│  React SPA   │ ───────────────────▶ │       FastAPI Gateway         │
│  (chat UI)   │ ◀─────────────────── │   POST /agents  GET /agents   │
└──────────────┘                      │   POST /chat    GET /health   │
                                       │   GET /agents/{id}/outputs    │
                                       └──────────────┬────────────────┘
                                                      │
                                              ┌───────▼────────┐
                                              │ SessionManager │  in-memory + JSON persistence
                                              └───────┬────────┘
                                                      │ ClaudeBackend (protocol)
                                       ┌──────────────┴───────────────┐
                                       │                              │
                              ┌────────▼─────────┐          ┌─────────▼────────┐
                              │ CliSubprocess    │          │   MockBackend    │
                              │ `claude -p`      │          │ (tests / offline)│
                              │ --output-format  │          └──────────────────┘
                              │ json --resume    │
                              │ (subscription)   │
                              └──────────────────┘
```

- **Backend interface (`ClaudeBackend`)** decouples the platform from *how* Claude is
  reached. The CLI backend uses the subscription; the mock backend powers tests and
  offline demos. Swapping to the API/SDK later is a one-file change.
- **Sessions are stateful**: the `claude` session id is captured on the first message
  and reused via `--resume`, so multi-turn context is preserved.

## Repository layout

```
multi-agent-system/
├─ backend/         FastAPI gateway + SessionManager + Claude backends (Python 3.11)
│  ├─ src/agent_platform/   {config, logging, models, core, api}
│  ├─ tests/                unit + integration (98% coverage)
│  ├─ Dockerfile            python:3.11-slim + claude CLI
│  └─ railway.json
├─ frontend/        React 19 + Vite + Tailwind SPA (bun)
│  └─ Dockerfile            build → nginx
├─ docker-compose.yml
├─ docs/            the four specification documents
└─ README.md        (this file)
```

## Quick start (local, without Docker)

**1. Authenticate the Claude CLI** (once, on this machine):

```bash
claude            # interactive login to your Max subscription
# CI/headless alternative: claude setup-token  → prints CLAUDE_CODE_OAUTH_TOKEN
```

**2. Backend:**

```bash
cd backend
uv venv --python 3.11 && uv pip install -e ".[dev]"
cp .env.example .env
uv run uvicorn agent_platform.api.main:app --reload --port 8000
```

**3. Frontend:**

```bash
cd frontend
bun install
cp .env.example .env       # VITE_API_BASE_URL=http://localhost:8000
bun run dev                # http://localhost:3000
```

Run the backend with `AGENT_BACKEND=mock` to develop offline (canned responses, no
Claude invocation).

## Quick start (Docker Compose)

```bash
# Provide a subscription token (does not bill API credits):
export CLAUDE_CODE_OAUTH_TOKEN=$(claude setup-token)
docker compose up --build
# UI:  http://localhost:3000
# API: http://localhost:8000/docs
```

Offline (no Claude, no token):

```bash
AGENT_BACKEND=mock docker compose up --build
```

## API

| Method | Path                         | Description                        |
|--------|------------------------------|------------------------------------|
| GET    | `/health`                    | Liveness probe                     |
| POST   | `/agents`                    | Create an agent → returns its `id` |
| GET    | `/agents`                    | List agents                        |
| POST   | `/chat`                      | `{agent_id, message}` → response   |
| GET    | `/agents/{agent_id}/outputs` | Agent interaction history          |

Standard envelopes:

```json
{ "status": "success", "data": { ... }, "timestamp": "..." }
{ "status": "error", "error": "...", "code": "...", "timestamp": "..." }
```

Error codes: `VALIDATION_ERROR` (400), `AGENT_NOT_FOUND` (404),
`BACKEND_ERROR` (502), `BACKEND_TIMEOUT` (504), `INTERNAL_ERROR` (500).

## Quality gates

```bash
cd backend
uv run pytest                 # 57 tests, 98% coverage (fails under 80%)
uv run ruff check . && uv run ruff format --check .
uv run pyright                # 0 errors

cd ../frontend
bun run build                 # tsc typecheck + production bundle
```

## Deploying to Railway

Two services from this repo, each built from its Dockerfile.

**Backend service**
1. New Railway project → *Deploy from GitHub repo*.
2. Set the service **root directory** to `backend/` (uses `backend/railway.json` →
   `Dockerfile`, healthcheck `/health`).
3. Add variables:
   - `CLAUDE_CODE_OAUTH_TOKEN` = output of `claude setup-token` (subscription token).
   - `AGENT_CORS_ORIGINS` = the frontend's public URL.
   - `AGENT_BACKEND` = `cli` (default).
   - `PORT` is provided by Railway automatically.
4. Deploy. Verify `https://<backend>.up.railway.app/health`.

**Frontend service**
1. Add a second service, root directory `frontend/`.
2. Build arg `VITE_API_BASE_URL` = the backend's public URL (Vite inlines it at
   build time, so a rebuild is needed if the backend URL changes).
3. Deploy. Open the public URL.

> Persistence note: the backend's JSON session store lives on the container
> filesystem (ephemeral on Railway). Attach a volume at `/data`, or move to
> PostgreSQL in a later phase, if sessions must survive restarts.

## Phase 0 success criteria — status

- [x] Docker container builds and runs locally
- [x] FastAPI server starts without errors
- [x] Can send a message to Claude Code and get a response (verified end-to-end on subscription)
- [x] Session Manager creates and manages sessions (with `--resume` continuity)
- [x] Type hints, structured logging (no prints), env-driven config (no hardcoded secrets)
- [x] 98% test coverage (target ≥ 80%); ruff + pyright clean
- [x] Railway-deployable (Dockerfiles + `railway.json`)
- [x] README, per-component docs, architecture diagram

## What's next (Phase 1)

Redis pub/sub message broker, a service registry, and a two-agent ping-pong — see
`docs/MVP_IMPLEMENTATION_PLAN.md`.
