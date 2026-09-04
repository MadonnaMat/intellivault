"""app.agent.nodes.commit"""

from __future__ import annotations

from uuid import uuid4

from app.agent.fetch import FetchedDoc
from app.agent.nodes import commit_node
from app.agent.schemas import StructuredResult
from tests.agent.conftest import FakeEmbedder, FakePool, edge_row, fake_deps, make_state, node_row
from tests.graph.conftest import FakeNeo4jDriver


async def test_creates_private_nodes_and_records_progress() -> None:
    existing_id = uuid4()
    result = StructuredResult.model_validate(
        {
            "entities": [
                {"temp_id": "e1", "name": "New Co", "kind": "org"},
                {"temp_id": "e2", "name": "Known", "kind": "org", "existing_id": str(existing_id)},
            ],
            "relationships": [
                {"from_ref": "e2", "to_ref": "e1", "kind": "spun_off"},
                {"from_ref": "e1", "to_ref": "ghost", "kind": "broken"},
            ],
        }
    )
    driver = FakeNeo4jDriver([node_row("New Co")], [edge_row()])
    pool = FakePool()
    out = await commit_node(make_state(structured=result), deps=fake_deps(driver=driver, pool=pool))

    assert len(out["committed_entity_ids"]) == 1  # e2 linked, not created
    assert len(out["committed_relationship_ids"]) == 1
    assert any("ghost" in note for note in out["skipped"])
    create = [p for q, p in driver.calls if "CREATE (e:Entity" in q][0]
    assert create["visibility"] == "private"
    assert any("array_append(committed_entity_ids" in q for q, _ in pool.calls)


async def test_embeds_each_new_entity() -> None:
    result = StructuredResult.model_validate(
        {"entities": [{"temp_id": "e1", "name": "New Co", "kind": "org", "attributes": {"x": 1}}]}
    )
    driver = FakeNeo4jDriver([node_row("New Co")], [{"id": "ok"}])
    embedder = FakeEmbedder(vector=[0.3, 0.4])
    out = await commit_node(
        make_state(structured=result),
        deps=fake_deps(driver=driver, pool=FakePool(), embedder=embedder),
    )
    assert len(out["committed_entity_ids"]) == 1
    assert embedder.calls == ['New Co (org)\n{"x": 1}']
    assert any("SET e.embedding" in q for q, _ in driver.calls)
    assert not any(n.startswith("embed ") for n in out["skipped"])


async def test_survives_an_embedding_failure() -> None:
    result = StructuredResult.model_validate(
        {"entities": [{"temp_id": "e1", "name": "New Co", "kind": "org"}]}
    )
    deps = fake_deps(
        driver=FakeNeo4jDriver([node_row("New Co")]),
        pool=FakePool(),
        embedder=FakeEmbedder(error=RuntimeError("ollama down")),
    )
    out = await commit_node(make_state(structured=result), deps=deps)
    assert len(out["committed_entity_ids"]) == 1
    assert any("embed New Co: ollama down" in n for n in out["skipped"])


async def test_attaches_every_fetched_url_to_each_new_entity() -> None:
    result = StructuredResult.model_validate(
        {"entities": [{"temp_id": "e1", "name": "New Co", "kind": "org"}]}
    )
    driver = FakeNeo4jDriver([node_row("New Co")], [], [{"id": "ok"}])  # create, attach, embed
    state = make_state(
        structured=result,
        documents=[
            FetchedDoc(url="https://a.example/x", text="a"),
            FetchedDoc(url="https://b.example/y", text="b"),
        ],
    )
    out = await commit_node(state, deps=fake_deps(driver=driver, pool=FakePool()))

    assert len(out["committed_entity_ids"]) == 1
    attach = [p for q, p in driver.calls if "SOURCED_FROM" in q][0]
    assert attach["urls"] == ["https://a.example/x", "https://b.example/y"]
    assert not any(n.startswith("attach sources") for n in out["skipped"])


async def test_survives_a_source_attach_failure() -> None:
    result = StructuredResult.model_validate(
        {"entities": [{"temp_id": "e1", "name": "New Co", "kind": "org"}]}
    )

    driver = FakeNeo4jDriver([node_row("New Co")])
    original_run = driver.session

    calls = {"n": 0}

    def flaky_session(**kwargs: object) -> object:
        calls["n"] += 1
        if calls["n"] == 2:  # the attach_sources call
            raise RuntimeError("neo4j down")
        return original_run(**kwargs)

    driver.session = flaky_session  # type: ignore[assignment]
    state = make_state(
        structured=result, documents=[FetchedDoc(url="https://a.example/x", text="a")]
    )

    out = await commit_node(state, deps=fake_deps(driver=driver, pool=FakePool()))

    assert len(out["committed_entity_ids"]) == 1
    assert any("attach sources" in n and "neo4j down" in n for n in out["skipped"])


async def test_routes_a_rejected_edge_into_skipped() -> None:
    result = StructuredResult.model_validate(
        {
            "entities": [{"temp_id": "e1", "name": "A", "kind": "org"}],
            "relationships": [{"from_ref": "e1", "to_ref": "e1", "kind": "self"}],
        }
    )
    driver = FakeNeo4jDriver([node_row("A")], [], [])  # create_rel [] -> endpoints [] -> 404
    out = await commit_node(
        make_state(structured=result), deps=fake_deps(driver=driver, pool=FakePool())
    )
    assert out["committed_relationship_ids"] == []
    assert any("e1->e1" in note for note in out["skipped"])
