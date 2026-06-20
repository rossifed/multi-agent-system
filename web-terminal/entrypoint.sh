#!/usr/bin/env bash
#
# Launch ttyd serving an interactive login shell (with the `claude` CLI available).
# Refuses to start without basic-auth credentials so the terminal is never exposed
# open to the internet.
set -euo pipefail

# --- Security gate: never run an unauthenticated terminal ---
if [[ -z "${TTYD_USERNAME:-}" || -z "${TTYD_PASSWORD:-}" ]]; then
    echo "FATAL: TTYD_USERNAME and TTYD_PASSWORD must be set (web terminal auth)." >&2
    exit 1
fi

PORT="${PORT:-7681}"
WORKSPACE="${WORKSPACE_DIR:-/data/workspace}"
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-/data/claude}"

mkdir -p "$CONFIG_DIR" "$WORKSPACE"

# Optional convenience: clone a repo on first boot when the workspace is empty.
if [[ -n "${WORKSPACE_REPO:-}" && -z "$(ls -A "$WORKSPACE" 2>/dev/null)" ]]; then
    echo "Cloning ${WORKSPACE_REPO} into ${WORKSPACE} ..."
    git clone "${WORKSPACE_REPO}" "$WORKSPACE" || echo "WARN: clone failed; starting with an empty workspace."
fi

cd "$WORKSPACE"

echo "Starting ttyd on port ${PORT} (workspace: ${WORKSPACE}, claude config: ${CONFIG_DIR})"
# -d 7        : verbose logging (logs client connects + child process spawn/exit)
# --ping-interval 30 : send WS pings so the Railway proxy doesn't drop an idle
#                      connection (a likely cause of the reconnect loop)
# TTYD_DEBUG / TTYD_PING_INTERVAL let us tune these from Railway without a rebuild.
exec ttyd \
    --port "$PORT" \
    --credential "${TTYD_USERNAME}:${TTYD_PASSWORD}" \
    --writable \
    --debug "${TTYD_DEBUG:-7}" \
    --ping-interval "${TTYD_PING_INTERVAL:-30}" \
    --terminal-type xterm-256color \
    -t titleFixed="Claude Cloud Terminal" \
    -t fontSize=14 \
    bash -l
