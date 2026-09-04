"""app.agent.nodes.plan"""

from __future__ import annotations

from app.agent.nodes import plan_node
from app.agent.schemas import Plan
from tests.agent.conftest import FakeChatModel, fake_deps, make_state
from tests.graph.conftest import FakeNeo4jDriver


async def test_plan_node_produces_a_plan() -> None:
    chat = FakeChatModel(structured={"Plan": [{"summary": "look into it", "queries": ["a", "b"]}]})
    deps = fake_deps(driver=FakeNeo4jDriver(), chat_model=chat)
    out = await plan_node(make_state(), deps=deps)
    assert out["plan"] == Plan(summary="look into it", queries=["a", "b"])
