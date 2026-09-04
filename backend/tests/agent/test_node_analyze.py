"""app.agent.nodes.analyze — the fan-out (analyze_one) + fan-in (synthesize)."""

from __future__ import annotations

from typing import Any

from app.agent.fetch import FetchedDoc
from app.agent.nodes import analyze_one_node, synthesize_node, text_of
from tests.agent.conftest import FakeChatModel, fake_deps, make_state
from tests.graph.conftest import FakeNeo4jDriver


async def test_analyze_one_produces_one_note_per_source() -> None:
    deps = fake_deps(driver=FakeNeo4jDriver(), chat_model=FakeChatModel(text="a fact"))
    out = await analyze_one_node(
        {"topic": "t", "document": FetchedDoc(url="https://s.test/1", text="body")}, deps=deps
    )
    assert out["source_notes"] == ["<https://s.test/1> a fact"]


async def test_analyze_one_drops_a_source_whose_llm_call_fails() -> None:
    class _Boom(FakeChatModel):
        async def ainvoke(self, _messages: object) -> Any:
            raise TimeoutError("model too slow")

    deps = fake_deps(driver=FakeNeo4jDriver(), chat_model=_Boom())
    out = await analyze_one_node(
        {"topic": "t", "document": FetchedDoc(url="https://s.test/1", text="body")}, deps=deps
    )
    assert out["source_notes"] == []  # no reducer on `skipped` -> just drop the note


async def test_synthesize_folds_the_notes() -> None:
    deps = fake_deps(driver=FakeNeo4jDriver(), chat_model=FakeChatModel(text="merged"))
    out = await synthesize_node(make_state(source_notes=["<a> one", "<b> two"]), deps=deps)
    assert out["analysis"] == "merged"


async def test_synthesize_with_no_notes_is_a_noop() -> None:
    deps = fake_deps(driver=FakeNeo4jDriver())
    out = await synthesize_node(make_state(source_notes=[]), deps=deps)
    assert out["analysis"] == "(no sources were analysed)"


def test_text_of_flattens_list_and_non_string_content() -> None:
    assert text_of(["a", "b"]) == "a b"
    assert text_of(42) == "42"
    assert text_of("plain") == "plain"


def test_coerce_mcp_unwraps_text_content_blocks() -> None:
    from app.agent.nodes._common import coerce_mcp

    assert coerce_mcp([{"type": "text", "text": '{"a": 1}'}]) == {"a": 1}
    assert coerce_mcp([{"type": "text", "text": "just words"}]) == "just words"
    assert coerce_mcp({"already": "parsed"}) == {"already": "parsed"}
