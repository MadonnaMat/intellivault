"""app.agent.nodes.lookup — Wikipedia enrichment of the drafts."""

from __future__ import annotations

from app.agent.nodes import lookup_node
from app.agent.schemas import StructuredResult
from tests.agent.conftest import FakeTool, fake_deps, fake_wikipedia_tools, make_state
from tests.graph.conftest import FakeNeo4jDriver

_DRAFT = StructuredResult.model_validate(
    {
        "entities": [
            {"temp_id": "e1", "name": "Bell Labs", "kind": "org"},
            {"temp_id": "e2", "name": "William Shockley", "kind": "person"},
        ],
        "relationships": [],
    }
)


async def test_lookup_adds_summaries_and_cross_links() -> None:
    wiki = fake_wikipedia_tools(
        search_wikipedia={"results": [{"title": "Bell Labs"}]},
        get_summary={"summary": "An industrial research lab."},
        get_related_topics={"related": ["William Shockley"]},
    )
    deps = fake_deps(driver=FakeNeo4jDriver(), wikipedia_tools=wiki)
    out = await lookup_node(make_state(structured=_DRAFT), deps=deps)

    result = out["structured"]
    assert result.entities[0].attributes["wikipedia_summary"] == "An industrial research lab."
    # a related topic that matches another draft entity becomes an edge
    assert ("e1", "e2", "related_to") in {
        (r.from_ref, r.to_ref, r.kind) for r in result.relationships
    }


async def test_lookup_is_best_effort_per_entity() -> None:
    class _Boom(FakeTool):
        async def ainvoke(self, _args: object) -> object:
            raise RuntimeError("wiki down")

    wiki: dict[str, FakeTool] = {
        n: _Boom(n) for n in ("search_wikipedia", "get_summary", "get_related_topics")
    }
    out = await lookup_node(
        make_state(structured=_DRAFT),
        deps=fake_deps(driver=FakeNeo4jDriver(), wikipedia_tools=wiki),
    )
    assert out["structured"].entities  # unchanged, still there
    assert any("lookup Bell Labs" in n for n in out["skipped"])


async def test_lookup_skips_an_empty_draft() -> None:
    out = await lookup_node(
        make_state(structured=StructuredResult()), deps=fake_deps(driver=FakeNeo4jDriver())
    )
    assert out == {}
