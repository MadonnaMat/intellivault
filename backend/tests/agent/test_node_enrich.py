"""app.agent.nodes.enrich — cross-linking new entities into the existing graph."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.agent.nodes import enrich_node
from app.agent.schemas import DigestEntity
from tests.agent.conftest import (
    FakeChatModel,
    FakeEmbedder,
    FakePool,
    fake_deps,
    make_state,
    node_row,
)
from tests.graph.conftest import FakeNeo4jDriver


def _edge_ret(from_id: str, to_id: str) -> dict[str, object]:
    now = datetime(2026, 9, 3, tzinfo=UTC)
    return {
        "r": {
            "id": str(uuid4()),
            "owner_id": str(uuid4()),
            "kind": "informs",
            "visibility": "private",
            "created_at": now,
            "updated_at": now,
        },
        "from_id": from_id,
        "to_id": to_id,
    }


async def test_enrich_links_a_new_entity_to_a_vector_neighbour() -> None:
    new_id, neighbour_id = str(uuid4()), str(uuid4())
    new = DigestEntity(id=new_id, name="New Co", kind="org")
    neighbour = node_row("Old Co")
    neighbour["e"]["id"] = neighbour_id
    # search_entities_by_vector returns the neighbour; create_relationship returns a row
    driver = FakeNeo4jDriver([neighbour], [_edge_ret(new_id, neighbour_id)])
    chat = FakeChatModel(
        structured={"EnrichLinks": [{"links": [{"target_id": neighbour_id, "kind": "informs"}]}]}
    )
    out = await enrich_node(
        make_state(committed_entities=[new], committed_entity_ids=[new_id]),
        deps=fake_deps(
            driver=driver, pool=FakePool(), chat_model=chat, embedder=FakeEmbedder(vector=[0.1])
        ),
    )
    assert len(out["committed_relationship_ids"]) == 1


async def test_enrich_is_a_noop_without_committed_entities() -> None:
    deps = fake_deps(driver=FakeNeo4jDriver())
    out = await enrich_node(make_state(committed_entities=[]), deps=deps)
    assert out == {}


async def test_enrich_survives_an_embedder_failure() -> None:
    new = DigestEntity(id=str(uuid4()), name="New Co", kind="org")
    deps = fake_deps(
        driver=FakeNeo4jDriver(),
        pool=FakePool(),
        embedder=FakeEmbedder(error=RuntimeError("ollama down")),
    )
    out = await enrich_node(
        make_state(committed_entities=[new], committed_entity_ids=[str(new.id)]), deps=deps
    )
    assert out["committed_relationship_ids"] == []  # nothing linked, no crash


async def test_enrich_routes_a_rejected_link_into_skipped() -> None:
    new_id, neighbour_id = str(uuid4()), str(uuid4())
    new = DigestEntity(id=new_id, name="New Co", kind="org")
    neighbour = node_row("Old Co")
    neighbour["e"]["id"] = neighbour_id
    driver = FakeNeo4jDriver([neighbour], [], [])  # create_relationship [] -> endpoints [] -> 404
    chat = FakeChatModel(
        structured={"EnrichLinks": [{"links": [{"target_id": neighbour_id, "kind": "informs"}]}]}
    )
    out = await enrich_node(
        make_state(committed_entities=[new], committed_entity_ids=[new_id]),
        deps=fake_deps(
            driver=driver, pool=FakePool(), chat_model=chat, embedder=FakeEmbedder(vector=[0.1])
        ),
    )
    assert out["committed_relationship_ids"] == []
    assert any("enrich New Co" in n for n in out["skipped"])
