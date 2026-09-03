"""Numbered, tracked Cypher migrations for the knowledge graph.

Neo4j has **no built-in migration framework** (unlike Postgres + yoyo). The
community tool ``neo4j-migrations`` exists but is JVM-only, a heavy dependency
for a ``uv``-managed Python repo. This module is a deliberately small stand-in
that mirrors the yoyo workflow the rest of the project already uses:

* plain-Cypher files in ``backend/graph_migrations/`` named
  ``NNNN.description.cypher`` (with an optional matching ``.rollback.cypher``);
* applied migration ids are recorded as ``(:_GraphMigration {id})`` nodes **in
  the graph itself** — the same idea as yoyo's ``_yoyo_migration`` table;
* nothing runs automatically — ``make graph-migrate`` /
  ``docker compose run --rm graph-migrate`` / ``scripts/graph_migrate.py``.

Statements within a file are separated by ``;``. Neo4j schema statements cannot
share a transaction, so they run one-per-``session.run`` in file order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from neo4j import AsyncDriver, AsyncManagedTransaction, AsyncSession, Query

GRAPH_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "graph_migrations"

_LABEL = "_GraphMigration"
_RECORD = f"CREATE (m:{_LABEL} {{id: $id, applied_at: datetime()}})"
_UNRECORD = f"MATCH (m:{_LABEL} {{id: $id}}) DELETE m"

# Schema commands (CREATE/DROP CONSTRAINT/INDEX, including typed indexes like
# CREATE VECTOR INDEX / CREATE FULLTEXT INDEX) cannot share a transaction with a
# data write, so a schema-only migration runs its statements auto-commit and then
# records itself — safe because those statements are idempotent (IF NOT EXISTS /
# IF EXISTS). Anything else runs in one transaction with the tracking write, so a
# mid-way failure rolls the whole migration back.
_SCHEMA_STATEMENT = re.compile(
    r"^\s*(CREATE|DROP)\s+"
    r"(?:(?:VECTOR|FULLTEXT|TEXT|POINT|RANGE|LOOKUP)\s+)?"
    r"(CONSTRAINT|INDEX)\b",
    re.IGNORECASE,
)


def _is_schema_only(statements: tuple[str, ...]) -> bool:
    return bool(statements) and all(_SCHEMA_STATEMENT.match(s) for s in statements)


def _split_statements(text: str) -> list[str]:
    """Split a ``.cypher`` file into individual statements, dropping ``//`` comments."""
    body = "\n".join(line for line in text.splitlines() if not line.strip().startswith("//"))
    return [stmt.strip() for stmt in body.split(";") if stmt.strip()]


@dataclass(frozen=True)
class GraphMigration:
    """One numbered migration: its id and its forward / rollback statements."""

    id: str
    statements: tuple[str, ...]
    rollback: tuple[str, ...]


def load_graph_migrations(directory: Path = GRAPH_MIGRATIONS_DIR) -> list[GraphMigration]:
    """Load every ``NNNN.*.cypher`` (not ``*.rollback.cypher``) in name order."""
    migrations: list[GraphMigration] = []
    for path in sorted(directory.glob("*.cypher")):
        if path.name.endswith(".rollback.cypher"):
            continue
        rollback_path = path.parent / f"{path.stem}.rollback.cypher"
        rollback = (
            _split_statements(rollback_path.read_text(encoding="utf-8"))
            if rollback_path.exists()
            else []
        )
        migrations.append(
            GraphMigration(
                id=path.stem,
                statements=tuple(_split_statements(path.read_text(encoding="utf-8"))),
                rollback=tuple(rollback),
            )
        )
    return migrations


async def _applied_ids(session: AsyncSession) -> set[str]:
    result = await session.run(Query(f"MATCH (m:{_LABEL}) RETURN m.id AS id"))
    return {record["id"] async for record in result}


async def _run_steps_then_bookkeeping(
    tx: AsyncManagedTransaction, statements: tuple[str, ...], bookkeeping: str, migration_id: str
) -> None:
    for statement in statements:
        await tx.run(statement)
    await tx.run(bookkeeping, id=migration_id)


async def _apply_step(
    session: AsyncSession, statements: tuple[str, ...], bookkeeping: str, migration_id: str
) -> None:
    if _is_schema_only(statements):
        for statement in statements:
            await session.run(Query(statement))
        await session.run(Query(bookkeeping), id=migration_id)
    else:
        await session.execute_write(
            _run_steps_then_bookkeeping, statements, bookkeeping, migration_id
        )


async def apply_graph_migrations(
    driver: AsyncDriver,
    *,
    database: str = "neo4j",
    directory: Path = GRAPH_MIGRATIONS_DIR,
) -> list[str]:
    """Apply every not-yet-recorded migration. Returns the ids newly applied."""
    newly: list[str] = []
    async with driver.session(database=database) as session:
        done = await _applied_ids(session)
        for migration in load_graph_migrations(directory):
            if migration.id in done:
                continue
            await _apply_step(session, migration.statements, _RECORD, migration.id)
            newly.append(migration.id)
    return newly


async def rollback_graph_migrations(
    driver: AsyncDriver,
    *,
    database: str = "neo4j",
    directory: Path = GRAPH_MIGRATIONS_DIR,
) -> list[str]:
    """Roll back every applied migration, newest first. Returns the ids undone."""
    undone: list[str] = []
    async with driver.session(database=database) as session:
        done = await _applied_ids(session)
        for migration in reversed(load_graph_migrations(directory)):
            if migration.id not in done:
                continue
            await _apply_step(session, migration.rollback, _UNRECORD, migration.id)
            undone.append(migration.id)
    return undone


async def graph_migration_status(
    driver: AsyncDriver,
    *,
    database: str = "neo4j",
    directory: Path = GRAPH_MIGRATIONS_DIR,
) -> list[tuple[str, bool]]:
    """Return ``(id, applied)`` for every migration on disk, in order."""
    async with driver.session(database=database) as session:
        done = await _applied_ids(session)
    return [(m.id, m.id in done) for m in load_graph_migrations(directory)]
