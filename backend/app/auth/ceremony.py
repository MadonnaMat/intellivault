"""In-flight WebAuthn challenge storage.

A "begin" call stores the challenge it generated and drops the row id in the
short-lived ``iv_ceremony`` cookie; the matching "finish" call reads the cookie,
pops the row (single use) and verifies the browser's response against it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
from fastapi import Response

from app.auth.statements import sql

CEREMONY_COOKIE = "iv_ceremony"
_TTL = timedelta(minutes=5)


async def store_challenge(pool: asyncpg.Pool, challenge: bytes, user_id: UUID | None) -> UUID:
    """Persist a challenge (with the owning user for a registration) and return its id."""
    row = await pool.fetchrow(sql("store_challenge"), challenge, user_id, datetime.now(UTC) + _TTL)
    assert row is not None
    challenge_id: UUID = row["id"]
    return challenge_id


async def pop_challenge(
    pool: asyncpg.Pool, cookie_value: str | None
) -> tuple[bytes, UUID | None] | None:
    """Consume the challenge named by the cookie. Returns ``(challenge, user_id)``."""
    if not cookie_value:
        return None
    try:
        challenge_id = UUID(cookie_value)
    except ValueError:
        return None
    row = await pool.fetchrow(sql("pop_challenge"), challenge_id)
    if row is None:
        return None
    return row["challenge"], row["user_id"]


def set_ceremony_cookie(response: Response, challenge_id: UUID, secure: bool) -> None:
    response.set_cookie(
        CEREMONY_COOKIE,
        str(challenge_id),
        max_age=int(_TTL.total_seconds()),
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/auth",
    )


def clear_ceremony_cookie(response: Response, secure: bool) -> None:
    response.delete_cookie(
        CEREMONY_COOKIE, path="/auth", httponly=True, secure=secure, samesite="lax"
    )
