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
from app.graph.schemas import EntityInput, RelationshipInput, VisibilityChange
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
    # The edge to a private endpoint can only be private (see the rule below).
    await service.create_relationship(
        graph_driver,
        _ALICE,
        RelationshipInput(from_id=public_end.id, to_id=private_end.id, kind="links"),
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


async def test_cannot_link_two_public_entities_you_do_not_own(graph_driver: AsyncDriver) -> None:
    a = await service.create_entity(
        graph_driver, _ALICE, EntityInput(name="a", kind="n", visibility="public")
    )
    b = await service.create_entity(
        graph_driver, _ALICE, EntityInput(name="b", kind="n", visibility="public")
    )

    with pytest.raises(HTTPException) as exc:
        await service.create_relationship(
            graph_driver, _BOB, RelationshipInput(from_id=a.id, to_id=b.id, kind="x")
        )
    assert exc.value.status_code == 404


async def test_can_link_your_own_entity_to_a_public_one(graph_driver: AsyncDriver) -> None:
    mine = await service.create_entity(graph_driver, _BOB, EntityInput(name="mine", kind="n"))
    alices_public = await service.create_entity(
        graph_driver, _ALICE, EntityInput(name="pub", kind="n", visibility="public")
    )

    rel = await service.create_relationship(
        graph_driver, _BOB, RelationshipInput(from_id=mine.id, to_id=alices_public.id, kind="uses")
    )
    assert rel.kind == "uses"
    assert rel.visibility == "private"  # bob's node is private -> the edge must be too


async def test_public_edge_allowed_only_between_two_public_entities(
    graph_driver: AsyncDriver,
) -> None:
    pub_a = await service.create_entity(
        graph_driver, _ALICE, EntityInput(name="A", kind="n", visibility="public")
    )
    pub_b = await service.create_entity(
        graph_driver, _ALICE, EntityInput(name="B", kind="n", visibility="public")
    )
    priv = await service.create_entity(graph_driver, _ALICE, EntityInput(name="C", kind="n"))

    ok = await service.create_relationship(
        graph_driver,
        _ALICE,
        RelationshipInput(from_id=pub_a.id, to_id=pub_b.id, kind="k", visibility="public"),
    )
    assert ok.visibility == "public"

    with pytest.raises(HTTPException) as exc:
        await service.create_relationship(
            graph_driver,
            _ALICE,
            RelationshipInput(from_id=pub_a.id, to_id=priv.id, kind="k", visibility="public"),
        )
    assert exc.value.status_code == 422

    # a private edge to the same private endpoint is fine
    private_edge = await service.create_relationship(
        graph_driver,
        _ALICE,
        RelationshipInput(from_id=pub_a.id, to_id=priv.id, kind="k", visibility="private"),
    )
    assert private_edge.visibility == "private"


async def test_delete_entity_removes_it_and_its_edges(graph_driver: AsyncDriver) -> None:
    a, b = await _chain(graph_driver, _ALICE, "A", "B")

    await service.delete_entity(graph_driver, _ALICE, a)

    view = await service.list_graph(graph_driver, _ALICE)
    assert {e.name for e in view.entities} == {"B"}
    assert view.relationships == []


async def test_entity_owner_can_detach_an_edge_another_user_attached(
    graph_driver: AsyncDriver,
) -> None:
    alices = await service.create_entity(
        graph_driver, _ALICE, EntityInput(name="a", kind="n", visibility="public")
    )
    bobs = await service.create_entity(graph_driver, _BOB, EntityInput(name="b", kind="n"))
    rel = await service.create_relationship(
        graph_driver, _BOB, RelationshipInput(from_id=bobs.id, to_id=alices.id, kind="links")
    )

    # Alice owns an endpoint but not the edge — she can still detach it.
    await service.delete_relationship(graph_driver, _ALICE, str(rel.id))
    assert (await service.list_graph(graph_driver, _ALICE)).relationships == []


async def test_single_visibility_flip(graph_driver: AsyncDriver) -> None:
    entity = await service.create_entity(graph_driver, _ALICE, EntityInput(name="x", kind="n"))

    result = await service.change_visibility(
        graph_driver, _ALICE, str(entity.id), VisibilityChange(visibility="public")
    )

    assert result.affected_ids == [entity.id]
    assert {e.name for e in (await service.list_graph(graph_driver, _BOB)).entities} == {"x"}


async def test_visibility_change_on_another_users_entity_is_404(graph_driver: AsyncDriver) -> None:
    bobs = await service.create_entity(graph_driver, _BOB, EntityInput(name="b", kind="n"))

    with pytest.raises(HTTPException) as exc:
        await service.change_visibility(
            graph_driver, _ALICE, str(bobs.id), VisibilityChange(visibility="public")
        )

    assert exc.value.status_code == 404


async def _chain(graph_driver: AsyncDriver, owner: str, *names: str) -> list[str]:
    ids = []
    previous = None
    for name in names:
        entity = await service.create_entity(graph_driver, owner, EntityInput(name=name, kind="n"))
        ids.append(str(entity.id))
        if previous is not None:
            await service.create_relationship(
                graph_driver, owner, RelationshipInput(from_id=previous, to_id=entity.id, kind="r")
            )
        previous = entity.id
    return ids


async def test_cascade_promotes_the_connected_owned_subgraph(graph_driver: AsyncDriver) -> None:
    a, b, c = await _chain(graph_driver, _ALICE, "A", "B", "C")

    result = await service.change_visibility(
        graph_driver, _ALICE, a, VisibilityChange(visibility="public", cascade=True)
    )

    assert {str(i) for i in result.affected_ids} == {a, b, c}
    bob_view = await service.list_graph(graph_driver, _BOB)
    assert {e.name for e in bob_view.entities} == {"A", "B", "C"}
    assert [r.kind for r in bob_view.relationships] == ["r", "r"]  # both edges promoted too


async def test_cascade_stops_at_another_owners_node(graph_driver: AsyncDriver) -> None:
    mine = await service.create_entity(graph_driver, _ALICE, EntityInput(name="mine", kind="n"))
    bobs_public = await service.create_entity(
        graph_driver, _BOB, EntityInput(name="bobs", kind="n", visibility="public")
    )
    await service.create_relationship(
        graph_driver, _ALICE, RelationshipInput(from_id=mine.id, to_id=bobs_public.id, kind="r")
    )

    result = await service.change_visibility(
        graph_driver, _ALICE, str(mine.id), VisibilityChange(visibility="public", cascade=True)
    )

    assert {str(i) for i in result.affected_ids} == {str(mine.id)}


async def test_cascade_demote_is_symmetric(graph_driver: AsyncDriver) -> None:
    a = await service.create_entity(
        graph_driver, _ALICE, EntityInput(name="A", kind="n", visibility="public")
    )
    b = await service.create_entity(
        graph_driver, _ALICE, EntityInput(name="B", kind="n", visibility="public")
    )
    await service.create_relationship(
        graph_driver,
        _ALICE,
        RelationshipInput(from_id=a.id, to_id=b.id, kind="r", visibility="public"),
    )

    await service.change_visibility(
        graph_driver, _ALICE, str(a.id), VisibilityChange(visibility="private", cascade=True)
    )

    assert (await service.list_graph(graph_driver, _BOB)).entities == []


async def test_cascade_promotes_a_chain_longer_than_the_old_25_hop_cap(
    graph_driver: AsyncDriver,
) -> None:
    ids = await _chain(graph_driver, _ALICE, *[f"n{i}" for i in range(30)])

    result = await service.change_visibility(
        graph_driver, _ALICE, ids[0], VisibilityChange(visibility="public", cascade=True)
    )

    assert len(result.affected_ids) == 30
    assert len((await service.list_graph(graph_driver, _BOB)).entities) == 30


async def test_demote_to_private_demotes_own_public_edges_and_removes_foreign_ones(
    graph_driver: AsyncDriver,
) -> None:
    x = await service.create_entity(
        graph_driver, _ALICE, EntityInput(name="X", kind="n", visibility="public")
    )
    y = await service.create_entity(
        graph_driver, _ALICE, EntityInput(name="Y", kind="n", visibility="public")
    )
    await service.create_relationship(
        graph_driver,
        _ALICE,
        RelationshipInput(from_id=x.id, to_id=y.id, kind="own", visibility="public"),
    )
    bobs = await service.create_entity(
        graph_driver, _BOB, EntityInput(name="B", kind="n", visibility="public")
    )
    await service.create_relationship(
        graph_driver,
        _BOB,
        RelationshipInput(from_id=bobs.id, to_id=x.id, kind="bob", visibility="public"),
    )

    await service.change_visibility(
        graph_driver, _ALICE, str(x.id), VisibilityChange(visibility="private")
    )

    alice = await service.list_graph(graph_driver, _ALICE)
    assert [(r.kind, r.visibility) for r in alice.relationships] == [("own", "private")]
    assert (await service.list_graph(graph_driver, _BOB)).relationships == []  # bob's edge gone


async def test_cascade_demote_cleans_incident_edges_across_the_component(
    graph_driver: AsyncDriver,
) -> None:
    a = await service.create_entity(
        graph_driver, _ALICE, EntityInput(name="A", kind="n", visibility="public")
    )
    b = await service.create_entity(
        graph_driver, _ALICE, EntityInput(name="B", kind="n", visibility="public")
    )
    await service.create_relationship(
        graph_driver,
        _ALICE,
        RelationshipInput(from_id=a.id, to_id=b.id, kind="ab", visibility="public"),
    )
    bobs = await service.create_entity(
        graph_driver, _BOB, EntityInput(name="Bob", kind="n", visibility="public")
    )
    await service.create_relationship(
        graph_driver,
        _BOB,
        RelationshipInput(from_id=bobs.id, to_id=b.id, kind="bob", visibility="public"),
    )

    await service.change_visibility(
        graph_driver, _ALICE, str(a.id), VisibilityChange(visibility="private", cascade=True)
    )

    assert (await service.list_graph(graph_driver, _BOB)).relationships == []
    alice = await service.list_graph(graph_driver, _ALICE)
    assert [(r.kind, r.visibility) for r in alice.relationships] == [("ab", "private")]


async def test_cascade_reports_only_entities_that_actually_changed(
    graph_driver: AsyncDriver,
) -> None:
    already_public = await service.create_entity(
        graph_driver, _ALICE, EntityInput(name="pub", kind="n", visibility="public")
    )
    private = await service.create_entity(graph_driver, _ALICE, EntityInput(name="priv", kind="n"))
    await service.create_relationship(
        graph_driver,
        _ALICE,
        RelationshipInput(from_id=already_public.id, to_id=private.id, kind="r"),
    )

    result = await service.change_visibility(
        graph_driver, _ALICE, str(private.id), VisibilityChange(visibility="public", cascade=True)
    )

    assert result.affected_ids == [private.id]  # already_public was not "changed"


async def test_vector_search_respects_the_visibility_predicate(graph_driver: AsyncDriver) -> None:
    # 3-dim stand-in vectors; the index is 768-d but Neo4j only checks width on
    # write against the property, not the query vector — a short query vector
    # still returns ordered results for the test.
    await service.create_entity(graph_driver, _ALICE, EntityInput(name="alice-priv", kind="n"))
    alice_priv = (await service.list_graph(graph_driver, _ALICE)).entities[0]
    alice_pub = await service.create_entity(
        graph_driver, _ALICE, EntityInput(name="alice-pub", kind="n", visibility="public")
    )
    bob_priv = await service.create_entity(
        graph_driver, _BOB, EntityInput(name="bob-priv", kind="n")
    )

    vec = [0.1] * 768
    await service.set_entity_embedding(graph_driver, _ALICE, str(alice_priv.id), vec)
    await service.set_entity_embedding(graph_driver, _ALICE, str(alice_pub.id), vec)
    await service.set_entity_embedding(graph_driver, _BOB, str(bob_priv.id), vec)

    bob_hits = {
        e.name for e in await service.search_entities_by_vector(graph_driver, _BOB, vec, k=10)
    }
    assert bob_hits == {"bob-priv", "alice-pub"}  # never alice-priv


async def test_set_entity_embedding_rejects_a_foreign_entity(graph_driver: AsyncDriver) -> None:
    alice_pub = await service.create_entity(
        graph_driver, _ALICE, EntityInput(name="x", kind="n", visibility="public")
    )
    with pytest.raises(HTTPException) as exc:
        await service.set_entity_embedding(graph_driver, _BOB, str(alice_pub.id), [0.1] * 768)
    assert exc.value.status_code == 404
