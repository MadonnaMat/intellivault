"""Unit tests for the graph-migration loader and runner (no Neo4j)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from neo4j import AsyncDriver

from app.graph.migrations import (
    GRAPH_MIGRATIONS_DIR,
    _split_statements,
    apply_graph_migrations,
    load_graph_migrations,
    rollback_graph_migrations,
)


def test_split_statements_drops_comments_and_blanks() -> None:
    text = """
    // a comment
    CREATE CONSTRAINT a IF NOT EXISTS
    FOR (e:Entity) REQUIRE e.id IS UNIQUE;

    // another
    CREATE INDEX b IF NOT EXISTS FOR (e:Entity) ON (e.owner_id);
    """
    statements = _split_statements(text)
    assert len(statements) == 2
    assert statements[0].startswith("CREATE CONSTRAINT a")
    assert "//" not in "".join(statements)


def test_loads_0001_with_its_rollback() -> None:
    migrations = load_graph_migrations()
    assert [m.id for m in migrations] == [
        "0001.entity-and-relationship-schema",
        "0002.entity-vector-index",
    ]
    first = migrations[0]
    assert len(first.statements) == 4
    assert len(first.rollback) == 4
    assert all(s.startswith("CREATE ") for s in first.statements)
    assert all(s.startswith("DROP ") for s in first.rollback)

    vector = migrations[1]
    assert vector.statements[0].startswith("CREATE VECTOR INDEX entity_embedding")
    assert vector.rollback == ("DROP INDEX entity_embedding IF EXISTS",)


def test_migrations_dir_is_the_repo_directory() -> None:
    assert GRAPH_MIGRATIONS_DIR.name == "graph_migrations"
    assert (GRAPH_MIGRATIONS_DIR / "0001.entity-and-relationship-schema.cypher").exists()


# --- fake driver ---------------------------------------------------------


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def __aiter__(self) -> Any:
        return _AsyncRows(self._rows)


class _AsyncRows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._it = iter(rows)

    def __aiter__(self) -> _AsyncRows:
        return self

    async def __anext__(self) -> dict[str, Any]:
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration from None


_Calls = list[tuple[str, dict[str, Any]]]


def _record_run(
    driver: _FakeDriver, bucket: _Calls, query: Any, params: dict[str, Any]
) -> _FakeResult:
    text = getattr(query, "text", query)
    driver.calls.append((text, params))
    bucket.append((text, params))
    if text.startswith("MATCH (m:_GraphMigration) RETURN"):
        return _FakeResult([{"id": mid} for mid in driver.applied])
    return _FakeResult([])


class _FakeTx:
    def __init__(self, driver: _FakeDriver) -> None:
        self._driver = driver

    async def run(self, query: Any, **params: Any) -> _FakeResult:
        return _record_run(self._driver, self._driver.tx_calls, query, params)


class _FakeSession:
    def __init__(self, driver: _FakeDriver) -> None:
        self._driver = driver

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def run(self, query: Any, **params: Any) -> _FakeResult:
        return _record_run(self._driver, self._driver.session_calls, query, params)

    async def execute_write(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        return await fn(_FakeTx(self._driver), *args, **kwargs)


class _FakeDriver:
    def __init__(self, applied: list[str] | None = None) -> None:
        self.applied = applied or []
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.session_calls: list[tuple[str, dict[str, Any]]] = []
        self.tx_calls: list[tuple[str, dict[str, Any]]] = []

    def session(self, **_: Any) -> _FakeSession:
        return _FakeSession(self)


async def test_apply_runs_pending_and_records_them() -> None:
    driver = _FakeDriver()
    applied = await apply_graph_migrations(cast(AsyncDriver, driver))

    assert applied == ["0001.entity-and-relationship-schema", "0002.entity-vector-index"]
    texts = [t for t, _ in driver.calls]
    assert sum(t.startswith("CREATE CONSTRAINT") for t in texts) == 1
    assert sum(t.startswith("CREATE INDEX") for t in texts) == 3
    assert sum(t.startswith("CREATE VECTOR INDEX") for t in texts) == 1
    assert any(t.startswith("CREATE (m:_GraphMigration") for t in texts)


async def test_apply_skips_already_recorded() -> None:
    driver = _FakeDriver(
        applied=["0001.entity-and-relationship-schema", "0002.entity-vector-index"]
    )
    applied = await apply_graph_migrations(cast(AsyncDriver, driver))
    assert applied == []
    assert not any(t.startswith("CREATE ") for t, _ in driver.calls)


async def test_rollback_undoes_recorded_only() -> None:
    driver = _FakeDriver(applied=["0001.entity-and-relationship-schema"])
    undone = await rollback_graph_migrations(cast(AsyncDriver, driver))

    assert undone == ["0001.entity-and-relationship-schema"]
    texts = [t for t, _ in driver.calls]
    assert sum(t.startswith("DROP ") for t in texts) == 4
    assert any(t.startswith("MATCH (m:_GraphMigration {id: $id}) DELETE") for t in texts)


async def test_rollback_noop_when_nothing_applied() -> None:
    driver = _FakeDriver()
    assert await rollback_graph_migrations(cast(AsyncDriver, driver)) == []


def test_missing_rollback_file_is_tolerated(tmp_path: Path) -> None:
    (tmp_path / "0009.forward-only.cypher").write_text(
        "CREATE INDEX x IF NOT EXISTS FOR (e:E) ON (e.k);"
    )
    migrations = load_graph_migrations(tmp_path)
    assert migrations[0].rollback == ()


async def test_schema_only_migration_runs_auto_commit_not_in_a_tx(tmp_path: Path) -> None:
    (tmp_path / "0002.index.cypher").write_text(
        "CREATE INDEX foo IF NOT EXISTS FOR (e:Entity) ON (e.foo);"
    )
    driver = _FakeDriver()

    await apply_graph_migrations(cast(AsyncDriver, driver), directory=tmp_path)

    assert driver.tx_calls == []  # schema commands never open a write transaction
    assert any("CREATE INDEX foo" in q for q, _ in driver.session_calls)
    assert any(q.startswith("CREATE (m:_GraphMigration") for q, _ in driver.session_calls)


async def test_data_migration_runs_in_one_transaction_with_its_bookkeeping(
    tmp_path: Path,
) -> None:
    (tmp_path / "0002.backfill.cypher").write_text("MATCH (e:Entity) SET e.tag = 'x';")
    driver = _FakeDriver()

    applied = await apply_graph_migrations(cast(AsyncDriver, driver), directory=tmp_path)

    assert applied == ["0002.backfill"]
    tx_texts = [q for q, _ in driver.tx_calls]
    assert any("SET e.tag" in q for q in tx_texts)
    assert any(q.startswith("CREATE (m:_GraphMigration") for q in tx_texts)
