"""app.agent.nodes.survey"""

from __future__ import annotations

from app.agent.nodes import survey_graph_node
from app.agent.schemas import GraphDigest, Plan
from app.config import Settings
from tests.agent.conftest import OWNER, FakeEmbedder, edge_row, fake_deps, make_state, node_row
from tests.graph.conftest import FakeNeo4jDriver

_CAP1 = Settings(
    _env_file=None,
    NEO4J_PASSWORD="n",
    DATABASE_URL="postgresql://u:p@localhost:5432/db",
    AGENT_SURVEY_MAX_ENTITIES="1",
)


async def test_scopes_by_owner_and_builds_a_digest() -> None:
    driver = FakeNeo4jDriver([node_row("Bell Labs")], [])
    out = await survey_graph_node(make_state(), deps=fake_deps(driver=driver))

    digest = out["existing_graph"]
    assert isinstance(digest, GraphDigest)
    assert [e.name for e in digest.entities] == ["Bell Labs"]
    assert all(params["owner_id"] == OWNER for _q, params in driver.calls)
    assert out["skipped"] == []


async def test_caps_and_ranks_by_topic_relevance() -> None:
    entities = [node_row("Unrelated Widget"), node_row("Transistor History"), node_row("Also Off")]
    edge = edge_row()
    edge["from_id"] = entities[1]["e"]["id"]
    edge["to_id"] = entities[0]["e"]["id"]
    driver = FakeNeo4jDriver(entities, [edge])

    out = await survey_graph_node(
        make_state(plan=Plan(summary="s", queries=["transistor invention"])),
        deps=fake_deps(driver=driver, settings=_CAP1),
    )
    digest = out["existing_graph"]
    assert [e.name for e in digest.entities] == ["Transistor History"]
    assert digest.relationships == []  # the edge's other endpoint was dropped
    assert out["skipped"] == ["survey: showing 1 of 3 visible entities"]


async def test_prefers_vector_search_hits() -> None:
    a, b = node_row("Alpha Corp"), node_row("Beta Inst")
    driver = FakeNeo4jDriver([a, b], [], [{**b, "score": 0.9}])
    embedder = FakeEmbedder(vector=[0.5, 0.5])

    out = await survey_graph_node(
        make_state(plan=Plan(summary="s", queries=["beta institute"])),
        deps=fake_deps(driver=driver, embedder=embedder),
    )
    assert [e.name for e in out["existing_graph"].entities] == ["Beta Inst"]
    assert embedder.calls
    assert out["skipped"] == ["survey: showing 1 of 2 visible entities"]


async def test_falls_back_when_vector_search_is_empty() -> None:
    driver = FakeNeo4jDriver([node_row("Only One")], [])
    out = await survey_graph_node(
        make_state(), deps=fake_deps(driver=driver, embedder=FakeEmbedder(vector=[0.1]))
    )
    assert [e.name for e in out["existing_graph"].entities] == ["Only One"]
