"""app.agent.search_mcp — resolving the SearXNG search tool from the MCP server."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.agent import search_mcp
from app.config import Settings

_SETTINGS = Settings(
    _env_file=None,
    NEO4J_PASSWORD="n",
    DATABASE_URL="postgresql://u:p@localhost:5432/db",
    AGENT_SEARCH_MCP_URL="http://search-mcp.test:8770/mcp",
)


class _FakeClient:
    last_connections: dict[str, Any] | None = None

    def __init__(self, connections: dict[str, Any]) -> None:
        type(self).last_connections = connections

    async def get_tools(self, *, server_name: str | None = None) -> list[Any]:
        assert server_name == "searxng"
        return [SimpleNamespace(name="fetch"), SimpleNamespace(name="search")]


def test_build_search_client_maps_settings_to_a_streamable_http_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_mcp, "MultiServerMCPClient", _FakeClient)
    search_mcp.build_search_client(_SETTINGS)
    assert _FakeClient.last_connections == {
        "searxng": {"url": "http://search-mcp.test:8770/mcp", "transport": "streamable_http"}
    }


async def test_load_search_tool_picks_the_search_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(search_mcp, "MultiServerMCPClient", _FakeClient)
    tool = await search_mcp.load_search_tool(_SETTINGS)
    assert tool.name == "search"


async def test_load_search_tool_raises_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    class _NoSearch(_FakeClient):
        async def get_tools(self, *, server_name: str | None = None) -> list[Any]:
            return [SimpleNamespace(name="fetch"), SimpleNamespace(name="extract")]

    monkeypatch.setattr(search_mcp, "MultiServerMCPClient", _NoSearch)
    with pytest.raises(LookupError, match="extract"):
        await search_mcp.load_search_tool(_SETTINGS)
