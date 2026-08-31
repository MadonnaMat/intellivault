"""Tests for app.config.Settings."""

from __future__ import annotations

import pytest

from app.config import Settings


def _make(**env: str) -> Settings:
    """Build Settings from an explicit env mapping, ignoring any .env file."""
    base = {"NEO4J_PASSWORD": "n", "POSTGRES_PASSWORD": "p"}
    return Settings(_env_file=None, **{**base, **env})  # type: ignore[arg-type]


def test_defaults() -> None:
    settings = _make()
    assert settings.neo4j_uri == "bolt://localhost:7687"
    assert settings.ollama_chat_model == "qwen3:8b"
    assert settings.cors_origins == ["http://localhost:3000"]


def test_cors_origins_split_from_csv() -> None:
    settings = _make(CORS_ORIGINS="http://a.test, http://b.test")
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_secrets_are_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_postgres_dsn_uses_secret_value() -> None:
    settings = _make(POSTGRES_PASSWORD="s3cret", POSTGRES_HOST="db")
    assert settings.postgres_dsn == "postgresql://intellivault:s3cret@db:5432/intellivault"
