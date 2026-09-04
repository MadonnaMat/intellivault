"""app.agent.search_graph — the search_knowledge_graph tool's LangGraph."""

from __future__ import annotations

from app.agent.search_graph import build_search_graph, initial_state
from tests.agent.conftest import OWNER, FakeEmbedder, edge_row, fake_deps, node_row
from tests.graph.conftest import FakeNeo4jDriver


async def test_vector_hit_skips_the_lexical_fallback_and_fetches_edges() -> None:
    driver = FakeNeo4jDriver([node_row("Bell Labs")], [edge_row()])
    deps = fake_deps(driver=driver, embedder=FakeEmbedder(vector=[0.1, 0.2, 0.3]))
    graph = build_search_graph(deps)

    result = await graph.ainvoke(initial_state(OWNER, "bell labs", 5))

    assert [e.name for e in result["entities"]] == ["Bell Labs"]
    assert len(result["relationships"]) == 1
    assert result["note"] is None
    # only 2 calls: the vector search, then the edge fetch — no lexical fallback
    assert len(driver.calls) == 2


async def test_no_vector_hits_falls_back_to_lexical_ranking() -> None:
    driver = FakeNeo4jDriver(
        [],  # vector search: no hits
        [node_row("Bell Labs"), node_row("Random Co")],  # list_graph entities
        [],  # list_graph relationships
        [edge_row()],  # fetch_edges among the kept entities
    )
    deps = fake_deps(driver=driver, embedder=FakeEmbedder(vector=[0.1, 0.2, 0.3]))
    graph = build_search_graph(deps)

    result = await graph.ainvoke(initial_state(OWNER, "bell labs", 5))

    # "Random Co" shares no token with the query — dropped, unlike Bell Labs.
    assert [e.name for e in result["entities"]] == ["Bell Labs"]
    assert len(result["relationships"]) == 1
    assert result["note"] is None


async def test_nothing_matches_anywhere_sets_a_note_and_skips_the_edge_fetch() -> None:
    driver = FakeNeo4jDriver(
        [],  # vector search: no hits
        [node_row("Random Co")],  # list_graph entities — no token overlap
        [],  # list_graph relationships
    )
    deps = fake_deps(driver=driver, embedder=FakeEmbedder(vector=[0.1, 0.2, 0.3]))
    graph = build_search_graph(deps)

    result = await graph.ainvoke(initial_state(OWNER, "bell labs", 5))

    assert result["entities"] == []
    assert result["relationships"] == []
    assert result["note"] == "no matching entities found in the knowledge graph"
    assert len(driver.calls) == 3  # no 4th call for edges — nothing to fetch them for


async def test_embedding_failure_falls_back_to_lexical() -> None:
    driver = FakeNeo4jDriver(
        [node_row("Bell Labs")],  # list_graph entities
        [],  # list_graph relationships
        [edge_row()],  # fetch_edges
    )
    deps = fake_deps(driver=driver, embedder=FakeEmbedder(error=RuntimeError("ollama down")))
    graph = build_search_graph(deps)

    result = await graph.ainvoke(initial_state(OWNER, "bell labs", 5))

    assert [e.name for e in result["entities"]] == ["Bell Labs"]
    assert len(driver.calls) == 3  # no vector-search call at all — embed raised first
