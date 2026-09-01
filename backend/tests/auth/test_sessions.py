"""Unit tests for session issuance/resolution and the auth cookies."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import Response

from app.auth import ceremony, sessions
from app.auth.schemas import SessionUser
from app.config import Settings

_USER_ID = uuid4()


def _settings(**env: str) -> Settings:
    base = {"NEO4J_PASSWORD": "n", "DATABASE_URL": "postgresql://u:p@localhost:5432/db"}
    return Settings(_env_file=None, **{**base, **env})  # type: ignore[arg-type]


class FakePool:
    """Records the last statement + args and replays a canned fetch result."""

    def __init__(self, fetchrow_result: Any = None) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self._fetchrow_result = fetchrow_result

    async def execute(self, query: str, *args: Any) -> str:
        self.calls.append((query, args))
        return "OK"

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append((query, args))
        return self._fetchrow_result


@pytest.mark.asyncio
async def test_issue_session_stores_only_a_hash() -> None:
    pool = FakePool()
    token = await sessions.issue_session(pool, _USER_ID, _settings())  # type: ignore[arg-type]

    assert len(token) > 20
    (query, args) = pool.calls[0]
    assert "INSERT INTO sessions" in query
    assert args[0] == _USER_ID
    assert args[1] == sessions._digest(token)
    assert token.encode() not in bytes(str(args), "utf-8")


@pytest.mark.asyncio
async def test_resolve_session_hit_and_miss() -> None:
    row = {"id": _USER_ID, "email": "a@b.com", "display_name": "Ada"}
    assert await sessions.resolve_session(FakePool(row), "tok") == SessionUser(  # type: ignore[arg-type]
        id=_USER_ID, email="a@b.com", display_name="Ada"
    )
    assert await sessions.resolve_session(FakePool(None), "tok") is None  # type: ignore[arg-type]


def test_session_cookie_attributes() -> None:
    response = Response()
    sessions.set_session_cookie(response, "tok", _settings(SESSION_COOKIE_SECURE="true"))
    header = response.headers["set-cookie"]
    assert header.startswith("iv_session=tok")
    assert "HttpOnly" in header
    assert "Path=/" in header
    assert "SameSite=lax" in header
    assert "Secure" in header
    assert "Max-Age=2592000" in header  # 720h


def test_session_cookie_not_secure_on_localhost() -> None:
    response = Response()
    sessions.set_session_cookie(response, "tok", _settings())
    assert "Secure" not in response.headers["set-cookie"]


def test_clear_session_cookie() -> None:
    response = Response()
    sessions.clear_session_cookie(response, _settings())
    header = response.headers["set-cookie"]
    assert header.startswith("iv_session=")
    assert "Max-Age=0" in header or "expires=" in header.lower()


@pytest.mark.asyncio
async def test_pop_challenge_rejects_bad_cookie() -> None:
    pool = FakePool()
    assert await ceremony.pop_challenge(pool, None) is None  # type: ignore[arg-type]
    assert await ceremony.pop_challenge(pool, "not-a-uuid") is None  # type: ignore[arg-type]
    assert pool.calls == []  # never hit the database


@pytest.mark.asyncio
async def test_pop_challenge_miss_returns_none() -> None:
    assert await ceremony.pop_challenge(FakePool(None), str(uuid4())) is None  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_pop_challenge_returns_context() -> None:
    uid = uuid4()
    pool = FakePool(
        {"challenge": b"abc", "user_id": uid, "email": "a@b.com", "display_name": "Ada"}
    )
    result = await ceremony.pop_challenge(pool, str(uuid4()))  # type: ignore[arg-type]
    assert result is not None
    assert result.challenge == b"abc"
    assert result.user_id == uid
    assert result.email == "a@b.com"
    assert result.display_name == "Ada"


@pytest.mark.asyncio
async def test_store_challenge_sweeps_then_inserts() -> None:
    pool = FakePool({"id": _USER_ID})
    await ceremony.store_challenge(pool, b"chal", email="a@b.com", display_name="Ada")  # type: ignore[arg-type]
    sweep, insert = pool.calls[0][0], pool.calls[1][0]
    assert "DELETE FROM webauthn_challenges WHERE expires_at < now()" in sweep
    assert "INSERT INTO webauthn_challenges" in insert
    assert pool.calls[1][1][:4] == (b"chal", None, "a@b.com", "Ada")


def test_ceremony_cookie_is_scoped_to_auth() -> None:
    response = Response()
    ceremony.set_ceremony_cookie(response, UUID(int=1), _settings())
    header = response.headers["set-cookie"]
    assert "Path=/auth" in header
    assert "HttpOnly" in header
    assert "Max-Age=300" in header


def test_cookies_honour_samesite_and_domain_config() -> None:
    settings = _settings(
        SESSION_COOKIE_SECURE="true",
        SESSION_COOKIE_SAMESITE="none",
        SESSION_COOKIE_DOMAIN=".example.com",
    )
    response = Response()
    sessions.set_session_cookie(response, "tok", settings)
    header = response.headers["set-cookie"]
    assert "SameSite=none" in header
    assert "Domain=.example.com" in header
    assert "Secure" in header
