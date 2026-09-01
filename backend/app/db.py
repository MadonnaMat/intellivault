"""Database access for request handlers.

The asyncpg pool is opened once in the app lifespan (``app.main.lifespan``) and
stashed on ``app.state.pg_pool``. Handlers depend on :func:`get_pool` rather than
touching ``app.state`` directly.
"""

from __future__ import annotations

import asyncpg
from fastapi import Request


def get_pool(request: Request) -> asyncpg.Pool:
    """Return the shared asyncpg connection pool."""
    pool: asyncpg.Pool = request.app.state.pg_pool
    return pool
