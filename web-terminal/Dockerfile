# Web terminal: the REAL interactive `claude` CLI, served to a browser via ttyd.
#
# This is a TTY-backed cloud dev box — full Claude Code power, reachable from a
# phone or any PC, behind HTTP basic auth. Because ttyd gives `claude` a real
# pseudo-terminal, the normal interactive login flow works here (paste-code, the
# documented container fallback): you authenticate once and the credentials are
# persisted on the /data volume via CLAUDE_CONFIG_DIR. No token is baked in.
FROM debian:bookworm-slim

ARG TTYD_VERSION=1.7.7

# Dev toolchain: git/openssh for repo work, the rest for a usable shell.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl git openssh-client bash less nano jq ripgrep \
    && rm -rf /var/lib/apt/lists/*

# ttyd (static x86_64 binary — Railway runs amd64).
RUN curl -fsSL -o /usr/local/bin/ttyd \
        "https://github.com/tsl0922/ttyd/releases/download/${TTYD_VERSION}/ttyd.x86_64" \
    && chmod +x /usr/local/bin/ttyd

# Claude Code CLI (native installer → /root/.local/bin, no Node.js needed).
RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH="/root/.local/bin:${PATH}"

# Disable the in-container auto-updater; persist Claude config + sessions on the volume.
ENV DISABLE_AUTOUPDATER=1 \
    CLAUDE_CONFIG_DIR=/data/claude \
    WORKSPACE_DIR=/data/workspace \
    PORT=7681

RUN mkdir -p /data/claude /data/workspace
WORKDIR /data/workspace

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 7681

# Healthcheck authenticates against ttyd's root (basic auth → needs creds).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS -u "${TTYD_USERNAME}:${TTYD_PASSWORD}" "http://localhost:${PORT}/" >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
