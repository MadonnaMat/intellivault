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


class FakeRecord:
    """Stands in for a ``neo4j.Record`` — accessed by key, like the real thing.

    Nested node/relationship values are plain dicts here; the service's mappers
    treat a graph ``Node``/``Relationship`` and a dict the same way.
    """

    def __init__(self, data: dict[str, object]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> object:
        return self._data[key]

    def get(self, key: str, default: object = None) -> object:
        return self._data.get(key, default)


class _FakeResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def __aiter__(self) -> _FakeRows:
        return _FakeRows([FakeRecord(row) for row in self._rows])

    async def values(self, *_keys: str) -> list[list[object]]:
        return [list(row.values()) for row in self._rows]

    async def single(self) -> FakeRecord | None:
        return FakeRecord(self._rows[0]) if self._rows else None


class _FakeRows:
    def __init__(self, records: list[FakeRecord]) -> None:
        self._it = iter(records)

    def __aiter__(self) -> _FakeRows:
        return self

    async def __anext__(self) -> FakeRecord:
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration from None


def _next_result(driver: FakeNeo4jDriver, query: object, params: dict[str, object]) -> _FakeResult:
    rows = driver._responses.pop(0) if driver._responses else []
    driver.calls.append((str(getattr(query, "text", query)), params))
    return _FakeResult(rows)


class _FakeTx:
    def __init__(self, driver: FakeNeo4jDriver) -> None:
        self._driver = driver

    async def run(self, query: object, **params: object) -> _FakeResult:
        return _next_result(self._driver, query, params)


class _FakeSession:
    def __init__(self, driver: FakeNeo4jDriver) -> None:
        self._driver = driver

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def run(self, query: object, **params: object) -> _FakeResult:
        return _next_result(self._driver, query, params)

    async def execute_write(self, fn: object, *args: object, **kwargs: object) -> object:
        return await fn(_FakeTx(self._driver), *args, **kwargs)  # type: ignore[operator]


class FakeNeo4jDriver:
    """A scripted async driver: each ``run`` (session or tx) returns the next queued row list."""

    def __init__(self, *responses: list[dict[str, object]]) -> None:
        self._responses: list[list[dict[str, object]]] = list(responses)
        self.calls: list[tuple[str, dict[str, object]]] = []

    def session(self, **_: object) -> _FakeSession:
        return _FakeSession(self)


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
