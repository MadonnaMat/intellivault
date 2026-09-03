"""app.agent.nodes.search — search_node, fetch_node, result parsing."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from app.agent.nodes import fetch_node, search_node
from app.agent.nodes.search import _parse_search_result
from app.agent.schemas import Plan, SearchHit
from tests.agent.conftest import FakeSearchTool, fake_deps, make_state
from tests.graph.conftest import FakeNeo4jDriver

pytestmark = pytest.mark.usefixtures("no_real_dns")


async def test_search_node_dedupes_caps_and_drops_ssrf_urls() -> None:
    results = [
        {"url": "https://a.test/1", "title": "A"},
        {"url": "https://a.test/1", "title": "dup"},
        {"url": "https://private.test/x", "title": "internal"},
        {"url": "https://b.test/2"},
        {"url": "https://c.test/3"},
        {"url": "https://d.test/4"},  # past AGENT_MAX_SOURCES=3
    ]
    deps = fake_deps(driver=FakeNeo4jDriver(), search_tool=FakeSearchTool(results))
    out = await search_node(make_state(plan=Plan(summary="s", queries=["q"])), deps=deps)

    assert [h.url for h in out["search_hits"]] == [
        "https://a.test/1",
        "https://b.test/2",
        "https://c.test/3",
    ]
    assert any("private.test" in note for note in out["skipped"])


async def test_search_node_no_plan_is_a_noop() -> None:
    out = await search_node(make_state(plan=None), deps=fake_deps(driver=FakeNeo4jDriver()))
    assert out["search_hits"] == []


@respx.mock
async def test_fetch_node_tolerates_a_per_url_failure() -> None:
    respx.get("https://ok.test/a").mock(return_value=httpx.Response(200, html="<p>hello</p>"))
    respx.get("https://bad.test/b").mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient(follow_redirects=False) as client:
        deps = fake_deps(driver=FakeNeo4jDriver(), http_client=client)
        out = await fetch_node(
            make_state(
                search_hits=[
                    SearchHit(url="https://ok.test/a"),
                    SearchHit(url="https://bad.test/b"),
                ]
            ),
            deps=deps,
        )
    assert [d.text for d in out["documents"]] == ["hello"]
    assert any("bad.test" in note for note in out["skipped"])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('[{"url": "https://a.test"}]', ["https://a.test"]),
        ({"results": [{"link": "https://b.test"}]}, ["https://b.test"]),
        ("not json", []),
        (12345, []),
        (["plain string", {"title": "no url"}], []),
        ([{"type": "text", "text": '[{"url": "https://mcp.test/1"}]'}], ["https://mcp.test/1"]),
        ([{"type": "text", "text": "not json either"}], []),
    ],
)
def test_parse_search_result_normalises_shapes(raw: Any, expected: list[str]) -> None:
    assert [h.url for h in _parse_search_result(raw)] == expected
