"""FastAPI dependencies that resolve the current user from the session cookie."""

from __future__ import annotations

from typing import Annotated

import asyncpg
from fastapi import Depends, HTTPException, Request, status

from app.auth.schemas import SessionUser
from app.auth.sessions import SESSION_COOKIE, resolve_session
from app.db import get_pool


async def current_user_optional(
    request: Request,
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
) -> SessionUser | None:
    """The signed-in user, or ``None`` when there is no valid session."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return await resolve_session(pool, token)


async def current_user(
    user: Annotated[SessionUser | None, Depends(current_user_optional)],
) -> SessionUser:
    """The signed-in user, or HTTP 401."""
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user
