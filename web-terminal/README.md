# Web Terminal — interactive Claude Code in the browser

A TTY-backed cloud dev box: the **real interactive `claude` CLI** served to your
browser (phone or PC) via [ttyd](https://github.com/tsl0922/ttyd), behind HTTP
basic auth. Full Claude Code power — identical to a local terminal — accessible
remotely. This is the "Option A" interim path while the streaming product GUI
(backend + frontend, "Option B") is built.

## Why this exists / how it differs from the FastAPI gateway

The `backend/` gateway drives `claude -p` (headless one-shot) — deterministic but
not the live interactive experience. This service runs the **actual interactive
TUI**: streaming output, live tool calls, full agent capabilities, no `-p`.

Because ttyd provides `claude` a genuine pseudo-terminal, the normal interactive
**login flow works here** — including the paste-code fallback documented for
containers. You authenticate once from your phone's browser; credentials persist
on the `/data` volume (`CLAUDE_CONFIG_DIR`).

## Configuration (environment variables)

| Variable | Required | Description |
|----------|----------|-------------|
| `TTYD_USERNAME` | **yes** | Basic-auth username. The container refuses to start without it. |
| `TTYD_PASSWORD` | **yes** | Basic-auth password — use a long random secret. |
| `PORT` | no | Listen port (Railway sets this automatically; defaults to `7681`). |
| `WORKSPACE_REPO` | no | Git URL to clone into the workspace on first boot (if empty). |
| `WORKSPACE_DIR` | no | Workspace path (default `/data/workspace`). |
| `CLAUDE_CONFIG_DIR` | no | Claude config/credentials/sessions dir (default `/data/claude`). |

> **Security:** there is no anonymous access — basic auth is mandatory and TLS is
> provided by Railway. The terminal grants a full shell with `claude` at full
> power; treat the credentials like a production secret. Hardening backlog:
> run as non-root, add a second auth factor, or front it with a private tunnel
> (Tailscale) to remove the public endpoint entirely.

## Run locally

```bash
cd web-terminal
docker build -t claude-web-terminal .
docker run --rm -p 7681:7681 \
  -e TTYD_USERNAME=admin -e TTYD_PASSWORD=change-me \
  -v "$PWD/.data:/data" \
  claude-web-terminal
# open http://localhost:7681  (login: admin / change-me)
```

## Deploy on Railway (dashboard)

1. **New service** in your Railway project → *Deploy from GitHub repo* → this repo,
   branch **`dev`**. Set the service **root directory** to `web-terminal/`
   (uses `web-terminal/railway.json` → `Dockerfile`).
2. **Volume:** attach a persistent volume mounted at **`/data`** (keeps your Claude
   login + session history + workspace across redeploys).
3. **Variables:**
   - `TTYD_USERNAME` = your chosen username.
   - `TTYD_PASSWORD` = a long random secret.
   - (optional) `WORKSPACE_REPO` = a git URL to auto-clone.
   - `PORT` is provided by Railway automatically.
4. **Deploy**, then open the public URL. Log in with your basic-auth credentials.

## First-time Claude login (once)

In the web terminal:

```bash
claude
```

Follow the prompt; if the browser shows a login **code** instead of redirecting
(normal in containers), paste it back at the `Paste code here if prompted`
prompt. Credentials are written to `/data/claude` and survive restarts.

Then just work normally: `cd` into a project, run `claude`, edit, commit, push.
