"""app.agent.nodes.search.broaden_queries_node"""

from __future__ import annotations

from app.agent.nodes import broaden_queries_node
from app.agent.schemas import Plan
from tests.agent.conftest import FakeChatModel, fake_deps, make_state
from tests.graph.conftest import FakeNeo4jDriver


async def test_broaden_replaces_queries_and_bumps_the_counter() -> None:
    payload = {"summary": "x", "queries": ["broad one", "broad two"]}
    chat = FakeChatModel(structured={"Plan": [payload]})
    deps = fake_deps(driver=FakeNeo4jDriver(), chat_model=chat)
    state = make_state(plan=Plan(summary="keep", queries=["narrow"]), search_attempts=0)

    out = await broaden_queries_node(state, deps=deps)

    assert out["plan"].queries == ["broad one", "broad two"]
    assert out["plan"].summary == "keep"  # only the queries change
    assert out["search_attempts"] == 1
    assert any("broadened queries" in n for n in out["skipped"])
