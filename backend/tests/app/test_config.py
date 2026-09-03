"""Tests for app.config.Settings."""

from __future__ import annotations

import pytest

from app.config import Settings

_DB_URL = "postgresql://u:p@localhost:5432/intellivault_test"


def _make(**env: str) -> Settings:
    """Build Settings from an explicit env mapping, ignoring any .env file."""
    base = {"NEO4J_PASSWORD": "n", "DATABASE_URL": _DB_URL}
    return Settings(_env_file=None, **{**base, **env})  # type: ignore[arg-type]


def test_defaults() -> None:
    settings = _make()
    assert settings.neo4j_uri == "bolt://localhost:7687"
    assert settings.ollama_chat_model == "qwen3:8b"
    assert settings.cors_origins == ["http://localhost:3000"]
    assert settings.docs_enabled is True
    assert _make(DOCS_ENABLED="false").docs_enabled is False


def test_webauthn_defaults() -> None:
    settings = _make()
    assert settings.webauthn_rp_id == "localhost"
    assert settings.webauthn_origin == "http://localhost:3000"
    assert settings.session_ttl_hours == 720
    assert settings.session_cookie_secure is False


def test_webauthn_overrides_from_env() -> None:
    settings = _make(
        WEBAUTHN_RP_ID="example.com",
        WEBAUTHN_ORIGIN="https://app.example.com",
        SESSION_COOKIE_SECURE="true",
        SESSION_COOKIE_SAMESITE="none",
    )
    assert settings.webauthn_rp_id == "example.com"
    assert settings.webauthn_origin == "https://app.example.com"
    assert settings.session_cookie_secure is True
    assert settings.session_cookie_samesite == "none"


def test_agent_defaults() -> None:
    settings = _make()
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.agent_fetch_timeout == 10.0
    assert settings.agent_fetch_max_redirects == 3
    assert settings.agent_fetch_max_bytes == 2_000_000
    assert settings.agent_source_char_limit == 12_000
    assert settings.agent_max_sources == 5
    assert settings.agent_survey_max_entities == 150
    assert settings.agent_search_mcp_url == "http://localhost:8770/mcp"
    assert settings.agent_worker_concurrency == 4


def test_agent_overrides_from_env() -> None:
    settings = _make(
        REDIS_URL="redis://redis:6379/1",
        AGENT_FETCH_MAX_BYTES="4096",
        AGENT_SOURCE_CHAR_LIMIT="500",
    )
    assert settings.redis_url == "redis://redis:6379/1"
    assert settings.agent_fetch_max_bytes == 4096
    assert settings.agent_source_char_limit == 500


def test_db_pool_bounds() -> None:
    assert _make().db_pool_min_size == 0
    assert _make().db_pool_max_size == 20
    assert _make(DB_POOL_MAX_SIZE="50").db_pool_max_size == 50


def test_blank_cookie_domain_is_none() -> None:
    assert _make().session_cookie_domain is None
    assert _make(SESSION_COOKIE_DOMAIN="").session_cookie_domain is None
    assert _make(SESSION_COOKIE_DOMAIN=".example.com").session_cookie_domain == ".example.com"


def test_cors_origins_split_from_csv() -> None:
    settings = _make(CORS_ORIGINS="http://a.test, http://b.test")
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_required_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_database_dsn_roundtrips() -> None:
    assert _make().database_dsn == _DB_URL
