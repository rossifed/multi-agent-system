# Backend image: FastAPI gateway + Claude Code CLI.
#
# The CLI is installed via the official native installer (no Node.js needed) and
# authenticates at RUNTIME via the CLAUDE_CODE_OAUTH_TOKEN env var (a subscription
# token from `claude setup-token`). No secret is baked into the image.
FROM python:3.11-slim

# System deps: curl to fetch the installer, ca-certificates for TLS.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install the Claude Code CLI (native binary into /root/.local/bin).
RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH="/root/.local/bin:${PATH}"
# Disable the background auto-updater inside the container.
ENV DISABLE_AUTOUPDATER=1

WORKDIR /app

# Install Python deps first (better layer caching).
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Sensible container defaults (override via env / Railway variables).
ENV AGENT_BACKEND=cli \
    AGENT_LOG_JSON=true \
    AGENT_SESSION_STORE_PATH=/data/sessions.json \
    PORT=8000

RUN mkdir -p /data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/health" || exit 1

# sh -c so ${PORT} (set by Railway) is expanded at runtime.
CMD ["sh", "-c", "uvicorn agent_platform.api.main:app --host 0.0.0.0 --port ${PORT}"]
