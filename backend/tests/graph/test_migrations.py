"""Integration: graph migrations apply, are idempotent, and roll back.

Runs against the disposable ``neo4j-test`` instance; self-skips when unreachable.
"""

from __future__ import annotations

from neo4j import AsyncDriver

from app.graph.migrations import (
    apply_graph_migrations,
    graph_migration_status,
    rollback_graph_migrations,
)
from tests.graph.conftest import requires_neo4j

pytestmark = requires_neo4j

_SCHEMA_NAMES = {
    "entity_id_unique",
    "entity_owner_visibility",
    "related_to_id",
    "related_to_owner_visibility",
    "entity_embedding",
}
_MIGRATION_IDS = ["0001.entity-and-relationship-schema", "0002.entity-vector-index"]


async def _schema_names(driver: AsyncDriver) -> set[str]:
    async with driver.session(database="neo4j") as session:
        constraints = await (await session.run("SHOW CONSTRAINTS YIELD name RETURN name")).values()
        indexes = await (await session.run("SHOW INDEXES YIELD name RETURN name")).values()
    return {row[0] for row in constraints + indexes}


async def test_apply_is_idempotent_and_registered(graph_driver: AsyncDriver) -> None:
    # conftest's graph_driver already applied every migration.
    assert await apply_graph_migrations(graph_driver) == []

    assert await _schema_names(graph_driver) >= _SCHEMA_NAMES
    assert await graph_migration_status(graph_driver) == [(mid, True) for mid in _MIGRATION_IDS]


async def test_rollback_then_reapply(graph_driver: AsyncDriver) -> None:
    undone = await rollback_graph_migrations(graph_driver)
    assert undone == list(reversed(_MIGRATION_IDS))
    assert _SCHEMA_NAMES.isdisjoint(await _schema_names(graph_driver))
    assert await graph_migration_status(graph_driver) == [(mid, False) for mid in _MIGRATION_IDS]

    reapplied = await apply_graph_migrations(graph_driver)
    assert reapplied == _MIGRATION_IDS
    assert await _schema_names(graph_driver) >= _SCHEMA_NAMES
