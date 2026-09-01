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
