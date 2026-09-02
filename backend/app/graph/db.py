"""Neo4j access for request handlers.

The async driver is opened once in the app lifespan (``app.main.lifespan``) and
stashed on ``app.state.neo4j_driver``. Handlers depend on :func:`get_driver`
rather than touching ``app.state`` directly — the mirror of :mod:`app.db` for
Postgres.
"""

from __future__ import annotations

from fastapi import Request
from neo4j import AsyncDriver


def get_driver(request: Request) -> AsyncDriver:
    """Return the shared Neo4j async driver."""
    driver: AsyncDriver = request.app.state.neo4j_driver
    return driver
