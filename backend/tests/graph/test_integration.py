"""Integration: property-level security against a real Neo4j.

Runs against the disposable ``neo4j-test`` instance; self-skips when unreachable.
These assert what only a real engine can prove — the ``WHERE`` predicate really
does hide another tenant's private data.
"""

from __future__ import annotations

from uuid import uuid4

from neo4j import AsyncDriver

from app.graph import service
from app.graph.schemas import EntityInput
from tests.graph.conftest import requires_neo4j

pytestmark = requires_neo4j

_ALICE = str(uuid4())
_BOB = str(uuid4())


async def test_caller_sees_own_private_and_all_public_only(graph_driver: AsyncDriver) -> None:
    await service.create_entity(graph_driver, _ALICE, EntityInput(name="alice-secret", kind="note"))
    await service.create_entity(
        graph_driver, _ALICE, EntityInput(name="alice-public", kind="note", visibility="public")
    )
    await service.create_entity(graph_driver, _BOB, EntityInput(name="bob-secret", kind="note"))
    await service.create_entity(
        graph_driver, _BOB, EntityInput(name="bob-public", kind="note", visibility="public")
    )

    alice_view = {e.name for e in (await service.list_graph(graph_driver, _ALICE)).entities}
    bob_view = {e.name for e in (await service.list_graph(graph_driver, _BOB)).entities}

    assert alice_view == {"alice-secret", "alice-public", "bob-public"}
    assert bob_view == {"bob-secret", "bob-public", "alice-public"}
    assert "bob-secret" not in alice_view
    assert "alice-secret" not in bob_view


async def test_create_entity_round_trips(graph_driver: AsyncDriver) -> None:
    created = await service.create_entity(
        graph_driver,
        _ALICE,
        EntityInput(name="Acme", kind="org", visibility="public", attributes={"tier": "gold"}),
    )

    (fetched,) = (await service.list_graph(graph_driver, _ALICE)).entities
    assert fetched.id == created.id
    assert fetched.attributes == {"tier": "gold"}
    assert fetched.owner_id == created.owner_id
    assert fetched.created_at == created.created_at
