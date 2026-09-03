"""app.agent.mcp_client + search_mcp + wikipedia_mcp."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from langchain_core.tools import BaseTool

from app.agent import mcp_client, search_mcp, wikipedia_mcp
from app.agent.mcp_client import index_by_name
from app.config import Settings
from tests.agent.conftest import FakeTool

_SETTINGS = Settings(
    _env_file=None,
    NEO4J_PASSWORD="n",
    DATABASE_URL="postgresql://u:p@localhost:5432/db",
    AGENT_SEARCH_MCP_URL="http://search-mcp.test:8770/mcp",
    AGENT_WIKIPEDIA_MCP_URL="http://wiki-mcp.test:8771/mcp",
)


class _FakeClient:
    last: dict[str, Any] | None = None
    tools: list[Any] = []

    def __init__(self, connections: dict[str, Any]) -> None:
        type(self).last = connections

    async def get_tools(self, *, server_name: str | None = None) -> list[Any]:
        return type(self).tools


def _patch(monkeypatch: pytest.MonkeyPatch, tools: list[Any]) -> None:
    _FakeClient.tools = tools
    monkeypatch.setattr(mcp_client, "MultiServerMCPClient", _FakeClient)


def test_index_by_name_keeps_both_the_bare_and_prefixed_aliases() -> None:
    tools = cast("list[BaseTool]", [FakeTool("wikipedia_get_summary"), FakeTool("get_summary")])
    idx = index_by_name(tools, strip_prefix="wikipedia")
    assert set(idx) == {"get_summary", "wikipedia_get_summary"}
    assert idx["get_summary"].name == "get_summary"  # the real bare tool wins


def test_index_by_name_aliases_a_prefixed_only_tool_to_its_bare_name() -> None:
    tools = cast("list[BaseTool]", [FakeTool("wikipedia_get_summary")])
    idx = index_by_name(tools, strip_prefix="wikipedia")
    assert idx["get_summary"].name == "wikipedia_get_summary"


def test_index_by_name_leaves_names_alone_without_a_prefix() -> None:
    tools = cast("list[BaseTool]", [FakeTool("wikipedia_get_summary")])
    assert set(index_by_name(tools)) == {"wikipedia_get_summary"}


async def test_load_mcp_tools_builds_a_streamable_http_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(monkeypatch, [SimpleNamespace(name="search")])
    await mcp_client.load_mcp_tools("http://x/mcp", "srv")
    assert _FakeClient.last == {"srv": {"url": "http://x/mcp", "transport": "streamable_http"}}


async def test_load_search_tool_picks_the_searxng_web_search_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(
        monkeypatch,
        [SimpleNamespace(name="web_url_read"), SimpleNamespace(name="searxng_web_search")],
    )
    tool = await search_mcp.load_search_tool(_SETTINGS)
    assert tool is not None and tool.name == "searxng_web_search"


async def test_load_search_tool_degrades_to_none_when_absent(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _patch(monkeypatch, [SimpleNamespace(name="extract")])
    with caplog.at_level("WARNING"):
        assert await search_mcp.load_search_tool(_SETTINGS) is None
    assert "search step is disabled" in caplog.text


async def test_load_wikipedia_tools_returns_the_wanted_set(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(
        monkeypatch,
        [SimpleNamespace(name=n) for n in wikipedia_mcp.WANTED]
        + [SimpleNamespace(name="wikipedia_get_summary")],
    )
    tools = await wikipedia_mcp.load_wikipedia_tools(_SETTINGS)
    assert set(tools) == set(wikipedia_mcp.WANTED)


async def test_load_wikipedia_tools_degrades_when_incomplete(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _patch(monkeypatch, [SimpleNamespace(name="search_wikipedia")])
    with caplog.at_level("WARNING"):
        tools = await wikipedia_mcp.load_wikipedia_tools(_SETTINGS)
    assert set(tools) == {"search_wikipedia"}  # the subset it found, no raise
    assert "lookup step is disabled" in caplog.text
