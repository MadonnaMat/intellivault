"""Shared fixtures for the graph tests.

The unit tests (``test_*_unit.py``, ``test_schemas.py``, ``test_db.py``,
``test_cypher_predicate.py``) need none of this and always run. The integration
tests (``test_integration.py``, ``test_migrations.py``) talk to the disposable
``neo4j-test`` instance (compose ``--profile test``) and self-skip when it is
unreachable, mirroring ``tests/auth/test_router.py``.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
import pytest_asyncio
from neo4j import AsyncDriver, AsyncGraphDatabase

from app.graph.migrations import apply_graph_migrations

TEST_NEO4J_URI = os.environ.get("NEO4J_TEST_URI", "bolt://localhost:7688")
TEST_NEO4J_USER = "neo4j"
TEST_NEO4J_PASSWORD = os.environ.get("NEO4J_TEST_PASSWORD", "testpassword")


async def _with_driver[T](work: Callable[[AsyncDriver], Awaitable[T]]) -> T:
    driver = AsyncGraphDatabase.driver(TEST_NEO4J_URI, auth=(TEST_NEO4J_USER, TEST_NEO4J_PASSWORD))
    try:
        return await work(driver)
    finally:
        await driver.close()


def _reachable() -> bool:
    async def _check(driver: AsyncDriver) -> bool:
        await driver.verify_connectivity()
        return True

    try:
        return asyncio.run(_with_driver(_check))
    except Exception:  # noqa: BLE001 - any failure means "skip the integration tests"
        return False


NEO4J_AVAILABLE = _reachable()
requires_neo4j = pytest.mark.skipif(not NEO4J_AVAILABLE, reason="neo4j-test not reachable")


@pytest_asyncio.fixture
async def graph_driver() -> AsyncIterator[AsyncDriver]:
    """A driver against ``neo4j-test`` — graph wiped, migrations applied, per test."""
    driver = AsyncGraphDatabase.driver(TEST_NEO4J_URI, auth=(TEST_NEO4J_USER, TEST_NEO4J_PASSWORD))
    async with driver.session(database="neo4j") as session:
        await session.run("MATCH (n) DETACH DELETE n")
    await apply_graph_migrations(driver)
    try:
        yield driver
    finally:
        await driver.close()
