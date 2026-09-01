"""In-flight WebAuthn challenge storage.

A "begin" call stores the challenge it generated and drops the row id in the
short-lived ``iv_ceremony`` cookie; the matching "finish" call reads the cookie,
pops the row (single use) and verifies the browser's response against it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
from fastapi import Response

from app.auth.cookies import clear_cookie, set_cookie
from app.auth.statements import sql
from app.config import Settings

CEREMONY_COOKIE = "iv_ceremony"
_TTL = timedelta(minutes=5)


@dataclass(frozen=True)
class Challenge:
    """A popped ceremony challenge plus whatever context the "begin" step stashed."""

    challenge: bytes
    user_id: UUID | None
    email: str | None
    display_name: str | None


async def store_challenge(
    pool: asyncpg.Pool,
    challenge: bytes,
    *,
    user_id: UUID | None = None,
    email: str | None = None,
    display_name: str | None = None,
) -> UUID:
    """Persist a challenge and return its id. Also sweeps expired rows."""
    await pool.execute("DELETE FROM webauthn_challenges WHERE expires_at < now()")
    row = await pool.fetchrow(
        sql("store_challenge"),
        challenge,
        user_id,
        email,
        display_name,
        datetime.now(UTC) + _TTL,
    )
    assert row is not None
    challenge_id: UUID = row["id"]
    return challenge_id


async def pop_challenge(pool: asyncpg.Pool, cookie_value: str | None) -> Challenge | None:
    """Consume the challenge named by the cookie."""
    if not cookie_value:
        return None
    try:
        challenge_id = UUID(cookie_value)
    except ValueError:
        return None
    row = await pool.fetchrow(sql("pop_challenge"), challenge_id)
    if row is None:
        return None
    return Challenge(
        challenge=row["challenge"],
        user_id=row["user_id"],
        email=row["email"],
        display_name=row["display_name"],
    )


def set_ceremony_cookie(response: Response, challenge_id: UUID, settings: Settings) -> None:
    set_cookie(
        response,
        CEREMONY_COOKIE,
        str(challenge_id),
        settings=settings,
        max_age=int(_TTL.total_seconds()),
        path="/auth",
    )


def clear_ceremony_cookie(response: Response, settings: Settings) -> None:
    clear_cookie(response, CEREMONY_COOKIE, settings=settings, path="/auth")
