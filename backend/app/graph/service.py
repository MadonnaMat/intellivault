"""Cypher behind the graph routes.

Single-statement operations go through :func:`_run` (one auto-commit
``session.run``, atomic on the server). The visibility cascade spans several
statements — a BFS over the caller-owned sub-graph plus two writes — so it runs
in one explicit write transaction (:func:`_cascade_visibility`) and is
all-or-nothing.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from neo4j import AsyncDriver, AsyncManagedTransaction, Query, Record

from app.graph.schemas import (
    Entity,
    EntityInput,
    GraphView,
    Relationship,
    RelationshipInput,
    VisibilityChange,
    VisibilityChangeResult,
)
from app.graph.statements import cypher

_DB = "neo4j"
_NOT_FOUND = status.HTTP_404_NOT_FOUND


async def _run(driver: AsyncDriver, statement: str, /, **params: Any) -> list[Record]:
    """Run one Cypher statement and return its records.

    Records are accessed by key. A ``RETURN e`` value is a graph ``Node`` and a
    ``RETURN r`` value a graph ``Relationship`` — both behave as a mapping of
    their properties (``node["id"]``), so the mappers below don't care whether
    they got a real graph object or a plain dict (from the test fakes). Note we
    do **not** use ``Record.data()``: it flattens a relationship to
    ``(start, type, end)`` and drops its properties.
    """
    async with driver.session(database=_DB) as session:
        result = await session.run(Query(statement), **params)
        return [record async for record in result]


def _dt(value: Any) -> datetime:
    """Coerce a Neo4j ``DateTime`` (or an already-native ``datetime``) to ``datetime``."""
    if isinstance(value, datetime):
        return value
    native: datetime = value.to_native()
    return native


def _entity(node: Mapping[str, Any]) -> Entity:
    raw_attributes = node.get("attributes")
    return Entity(
        id=node["id"],
        owner_id=node["owner_id"],
        visibility=node["visibility"],
        name=node["name"],
        kind=node["kind"],
        attributes=json.loads(raw_attributes) if raw_attributes else {},
        created_at=_dt(node["created_at"]),
        updated_at=_dt(node["updated_at"]),
    )


async def create_entity(driver: AsyncDriver, owner_id: str, data: EntityInput) -> Entity:
    rows = await _run(
        driver,
        cypher("create_entity"),
        id=str(uuid4()),
        owner_id=owner_id,
        visibility=data.visibility,
        name=data.name,
        kind=data.kind,
        attributes=json.dumps(data.attributes, sort_keys=True),
    )
    return _entity(rows[0]["e"])


def _relationship(row: Mapping[str, Any]) -> Relationship:
    edge = row["r"]
    return Relationship(
        id=edge["id"],
        owner_id=edge["owner_id"],
        from_id=row["from_id"],
        to_id=row["to_id"],
        kind=edge["kind"],
        visibility=edge["visibility"],
        created_at=_dt(edge["created_at"]),
        updated_at=_dt(edge["updated_at"]),
    )


async def create_relationship(
    driver: AsyncDriver, owner_id: str, data: RelationshipInput
) -> Relationship:
    rows = await _run(
        driver,
        cypher("create_relationship"),
        id=str(uuid4()),
        owner_id=owner_id,
        from_id=str(data.from_id),
        to_id=str(data.to_id),
        kind=data.kind,
        visibility=data.visibility,
    )
    if not rows:
        raise HTTPException(
            _NOT_FOUND,
            "Both entities must be visible to you and you must own at least one of them",
        )
    return _relationship(rows[0])


async def delete_entity(driver: AsyncDriver, owner_id: str, entity_id: str) -> None:
    rows = await _run(driver, cypher("delete_entity"), id=entity_id, owner_id=owner_id)
    if not rows:
        raise HTTPException(_NOT_FOUND, "Entity not found")


async def delete_relationship(driver: AsyncDriver, owner_id: str, relationship_id: str) -> None:
    rows = await _run(driver, cypher("delete_relationship"), id=relationship_id, owner_id=owner_id)
    if not rows:
        raise HTTPException(_NOT_FOUND, "Relationship not found")


async def list_graph(driver: AsyncDriver, owner_id: str) -> GraphView:
    # The two reads are independent (separate sessions) — run them concurrently.
    entity_rows, relationship_rows = await asyncio.gather(
        _run(driver, cypher("list_visible_entities"), owner_id=owner_id),
        _run(driver, cypher("list_visible_relationships"), owner_id=owner_id),
    )
    return GraphView(
        entities=[_entity(row["e"]) for row in entity_rows],
        relationships=[_relationship(row) for row in relationship_rows],
    )


async def _tx_run(tx: AsyncManagedTransaction, name: str, /, **params: Any) -> Any:
    """``tx.run`` for a named ``cypher/`` file.

    Unlike ``session.run``, ``tx.run`` rejects a ``Query`` wrapper and only types
    its query as ``LiteralString`` — hence the plain string plus the ignore.
    """
    return await tx.run(cypher(name), **params)


async def _owned_component(tx: AsyncManagedTransaction, owner_id: str, start_id: str) -> list[str]:
    """BFS out from ``start_id`` over caller-owned nodes and edges only."""
    seen = {start_id}
    frontier = {start_id}
    while frontier:
        result = await _tx_run(tx, "owned_neighbours", owner_id=owner_id, ids=list(frontier))
        found = {record["id"] async for record in result} - seen
        seen |= found
        frontier = found
    return list(seen)


async def _cascade_tx(
    tx: AsyncManagedTransaction, owner_id: str, entity_id: str, visibility: str
) -> list[str]:
    owned = await (
        await _tx_run(tx, "owned_entity_exists", id=entity_id, owner_id=owner_id)
    ).values()
    if not owned:
        raise HTTPException(_NOT_FOUND, "Entity not found")

    ids = await _owned_component(tx, owner_id, entity_id)
    entity_result = await _tx_run(
        tx, "flip_entities", ids=ids, owner_id=owner_id, visibility=visibility
    )
    changed_row = await entity_result.single()
    await _tx_run(tx, "flip_relationships", ids=ids, owner_id=owner_id, visibility=visibility)
    changed: list[str] = list(changed_row["changed"]) if changed_row else []
    return changed


async def _cascade_visibility(
    driver: AsyncDriver, owner_id: str, entity_id: str, visibility: str
) -> list[str]:
    async with driver.session(database=_DB) as session:
        result: list[str] = await session.execute_write(
            _cascade_tx, owner_id, entity_id, visibility
        )
        return result


async def change_visibility(
    driver: AsyncDriver, owner_id: str, entity_id: str, change: VisibilityChange
) -> VisibilityChangeResult:
    if change.cascade:
        affected = await _cascade_visibility(driver, owner_id, entity_id, change.visibility)
        return VisibilityChangeResult(affected_ids=affected)

    rows = await _run(
        driver,
        cypher("set_entity_visibility"),
        id=entity_id,
        owner_id=owner_id,
        visibility=change.visibility,
    )
    if not rows:
        raise HTTPException(_NOT_FOUND, "Entity not found")
    row = rows[0]
    return VisibilityChangeResult(affected_ids=[row["id"]] if row["changed"] else [])
