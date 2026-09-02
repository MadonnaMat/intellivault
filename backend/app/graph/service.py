"""Cypher behind the graph routes.

One private helper, :func:`_run`, is the sole ``driver.session()`` call site.
Everything else loads a statement from ``app/graph/cypher/`` and maps the
returned records to pydantic models. Each statement here is a single compound
Cypher query, which Neo4j runs atomically — so auto-commit ``session.run`` is
enough and there are no explicit transaction wrappers.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import uuid4

from neo4j import AsyncDriver, Query

from app.graph.schemas import Entity, EntityInput, GraphView
from app.graph.statements import cypher

_DB = "neo4j"


async def _run(driver: AsyncDriver, statement: str, /, **params: Any) -> list[Mapping[str, Any]]:
    """Run one Cypher statement and return its records as plain dicts."""
    async with driver.session(database=_DB) as session:
        result = await session.run(Query(statement), **params)
        return [record.data() async for record in result]


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


async def list_graph(driver: AsyncDriver, owner_id: str) -> GraphView:
    rows = await _run(driver, cypher("list_visible_entities"), owner_id=owner_id)
    return GraphView(entities=[_entity(row["e"]) for row in rows])
