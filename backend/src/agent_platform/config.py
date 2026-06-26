"""Application configuration.

All settings are loaded from environment variables (prefixed ``AGENT_``) or an
``.env`` file. No configuration value is hardcoded in the codebase.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the agent platform.

    Values are read from environment variables prefixed with ``AGENT_`` (e.g.
    ``AGENT_CLAUDE_BINARY``) or from a local ``.env`` file.
    """

    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Claude CLI backend ---
    claude_binary: str = Field(default="claude", description="Path to the claude executable.")
    claude_timeout_seconds: float = Field(default=120.0, gt=0, description="Per-invocation timeout.")
    claude_model: str | None = Field(default=None, description="Optional model override for the CLI.")
    backend: str = Field(default="cli", description='Backend implementation: "cli" or "mock".')

    # --- Claude tool permissions (locked down by default) ---
    # Space-separated allowlist passed to `--allowedTools` (e.g. "WebFetch WebSearch Read").
    # Empty/None = no tools allowed (the agent can only chat).
    claude_allowed_tools: str | None = Field(
        default=None,
        description="Space-separated tool allowlist for the CLI (--allowedTools).",
    )
    # Permission mode passed to `--permission-mode` (e.g. "acceptEdits", "bypassPermissions").
    # SECURITY: "bypassPermissions" lets the agent run any command / write any file with no
    # approval — only enable behind authentication and ideally in a sandboxed workspace.
    claude_permission_mode: str | None = Field(
        default=None,
        description="Permission mode for the CLI (--permission-mode).",
    )
    # Working directory the CLI runs in (and is granted via --add-dir). Scopes file access.
    claude_workspace_dir: str | None = Field(
        default=None,
        description="Working directory for the CLI subprocess (--add-dir).",
    )

    # --- Session persistence ---
    session_store_path: str | None = Field(
        default="./data/sessions.json",
        description="JSON file for session persistence. Empty/None disables persistence.",
    )

    # --- Inter-agent bus ---
    # Shared JSONL file the bus reads/writes. The API process and every agent's MCP
    # server must point at the SAME path (agents receive it via the BUS_FILE env var).
    bus_file: str = Field(
        default="./data/bus.jsonl",
        description="Shared JSONL bus file (also passed to agents' MCP servers as BUS_FILE).",
    )
    # How often the SSE stream polls the bus file for new messages (seconds).
    bus_stream_poll_seconds: float = Field(
        default=0.5,
        gt=0,
        description="Server-side poll interval for the SSE bus stream.",
    )

    # --- API / server ---
    log_level: str = Field(default="INFO", description="Root logging level.")
    log_json: bool = Field(default=False, description="Emit structured JSON logs when true.")
    # NoDecode: stop pydantic-settings from JSON-parsing the env var so the
    # validator below can accept a plain comma-separated string.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"],
        description="Allowed CORS origins for the web UI (comma-separated in env).",
    )

    @field_validator("backend")
    @classmethod
    def _validate_backend(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"cli", "mock"}:
            raise ValueError('backend must be "cli" or "mock"')
        return normalized

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Accept a comma-separated string (from env) or an already-parsed list."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator(
        "session_store_path",
        "claude_model",
        "claude_allowed_tools",
        "claude_permission_mode",
        "claude_workspace_dir",
        mode="before",
    )
    @classmethod
    def _empty_string_is_none(cls, value: object) -> object:
        """Treat an empty/whitespace env value as unset (None)."""
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance.

    Returns:
        The process-wide settings, instantiated once and cached.
    """
    return Settings()
