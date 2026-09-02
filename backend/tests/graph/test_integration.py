"""Integration: property-level security against a real Neo4j.

Runs against the disposable ``neo4j-test`` instance; self-skips when unreachable.
These assert what only a real engine can prove — the ``WHERE`` predicate really
does hide another tenant's private data.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from neo4j import AsyncDriver

from app.graph import service
from app.graph.schemas import EntityInput, RelationshipInput
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


async def test_relationship_hidden_when_an_endpoint_is_another_users_private(
    graph_driver: AsyncDriver,
) -> None:
    public_end = await service.create_entity(
        graph_driver, _ALICE, EntityInput(name="a-public", kind="n", visibility="public")
    )
    private_end = await service.create_entity(
        graph_driver, _ALICE, EntityInput(name="a-private", kind="n")
    )
    await service.create_relationship(
        graph_driver,
        _ALICE,
        RelationshipInput(
            from_id=public_end.id, to_id=private_end.id, kind="links", visibility="public"
        ),
    )

    # Bob can see the public endpoint but not the edge — its other end is
    # Alice's private node.
    bob_view = await service.list_graph(graph_driver, _BOB)
    assert bob_view.relationships == []
    assert {e.name for e in bob_view.entities} == {"a-public"}

    alice_view = await service.list_graph(graph_driver, _ALICE)
    assert [r.kind for r in alice_view.relationships] == ["links"]


async def test_create_relationship_rejects_an_invisible_endpoint(
    graph_driver: AsyncDriver,
) -> None:
    mine = await service.create_entity(graph_driver, _ALICE, EntityInput(name="mine", kind="n"))
    bobs_private = await service.create_entity(
        graph_driver, _BOB, EntityInput(name="bobs", kind="n")
    )

    with pytest.raises(HTTPException) as exc:
        await service.create_relationship(
            graph_driver,
            _ALICE,
            RelationshipInput(from_id=mine.id, to_id=bobs_private.id, kind="x"),
        )

    assert exc.value.status_code == 404
