"""Server-side sessions.

A session is an opaque random token handed to the browser in the ``iv_session``
cookie. Only its SHA-256 digest is stored, so a database leak cannot be replayed
as a live session. ``sessions.user_id`` is the ownerId downstream queries key
off.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
from fastapi import Response

from app.auth.cookies import clear_cookie, set_cookie
from app.auth.schemas import SessionUser
from app.auth.statements import sql
from app.config import Settings

SESSION_COOKIE = "iv_session"
_TOKEN_BYTES = 32


def _digest(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


async def issue_session(pool: asyncpg.Pool, user_id: UUID, settings: Settings) -> str:
    """Create a session for ``user_id`` and return its raw token."""
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    expires_at = datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours)
    await pool.execute(
        "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES ($1, $2, $3)",
        user_id,
        _digest(token),
        expires_at,
    )
    return token


async def resolve_session(pool: asyncpg.Pool, token: str) -> SessionUser | None:
    """Return the user for a live session token, bumping ``last_seen_at``."""
    row = await pool.fetchrow(sql("resolve_session"), _digest(token))
    if row is None:
        return None
    return SessionUser(id=row["id"], email=row["email"], display_name=row["display_name"])


async def revoke_session(pool: asyncpg.Pool, token: str) -> None:
    await pool.execute("DELETE FROM sessions WHERE token_hash = $1", _digest(token))


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    set_cookie(
        response,
        SESSION_COOKIE,
        token,
        settings=settings,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    clear_cookie(response, SESSION_COOKIE, settings=settings, path="/")
