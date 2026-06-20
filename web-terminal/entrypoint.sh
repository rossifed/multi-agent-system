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
exec ttyd \
    --port "$PORT" \
    --credential "${TTYD_USERNAME}:${TTYD_PASSWORD}" \
    --writable \
    --terminal-type xterm-256color \
    -t titleFixed="Claude Cloud Terminal" \
    -t fontSize=14 \
    bash -l
