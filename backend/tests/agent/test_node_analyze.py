"""app.agent.nodes.analyze (+ the shared text/format helpers)."""

from __future__ import annotations

from app.agent.nodes import analyze_node, text_of
from tests.agent.conftest import FakeChatModel, fake_deps, make_state
from tests.graph.conftest import FakeNeo4jDriver


async def test_analyze_node_returns_model_text() -> None:
    deps = fake_deps(driver=FakeNeo4jDriver(), chat_model=FakeChatModel(text="the notes"))
    out = await analyze_node(make_state(), deps=deps)
    assert out["analysis"] == "the notes"


def test_text_of_flattens_list_and_non_string_content() -> None:
    assert text_of(["a", "b"]) == "a b"
    assert text_of(42) == "42"
    assert text_of("plain") == "plain"
