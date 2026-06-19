"""Unit tests for configuration loading and validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_platform.config import Settings, get_settings


def test_defaults() -> None:
    settings = Settings()
    assert settings.claude_binary == "claude"
    assert settings.claude_timeout_seconds == 120.0
    assert settings.backend == "cli"
    assert settings.log_level == "INFO"


def test_backend_validator_normalizes_case() -> None:
    assert Settings(backend="MOCK").backend == "mock"


def test_backend_validator_rejects_unknown() -> None:
    with pytest.raises(ValidationError):
        Settings(backend="grpc")


def test_cors_origins_split_from_string() -> None:
    # The comma-separated form is how the value arrives from an env var.
    settings = Settings.model_validate({"cors_origins": "http://a.com, http://b.com ,"})
    assert settings.cors_origins == ["http://a.com", "http://b.com"]


def test_cors_origins_accepts_list() -> None:
    settings = Settings(cors_origins=["http://a.com"])
    assert settings.cors_origins == ["http://a.com"]


def test_cors_origins_from_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: a comma-separated env var must parse (no JSON decoding).
    monkeypatch.setenv("AGENT_CORS_ORIGINS", "http://localhost:3002, http://localhost:9999")
    settings = Settings()
    assert settings.cors_origins == ["http://localhost:3002", "http://localhost:9999"]


def test_empty_store_path_becomes_none() -> None:
    assert Settings(session_store_path="   ").session_store_path is None


def test_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(claude_timeout_seconds=0)


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
