"""Load the SearXNG web-search tool from the MCP server (streamable HTTP).

``langchain-mcp-adapters`` opens a fresh session per tool call, so the resolved
tool object is safe to build once per worker and share across concurrent runs.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.config import Settings

_SERVER = "searxng"
_SEARCH_TOOL = "search"


def build_client(settings: Settings) -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {_SERVER: {"url": settings.agent_search_mcp_url, "transport": "streamable_http"}}
    )


async def load_search_tool(settings: Settings) -> BaseTool:
    """Resolve the ``search`` tool exposed by the configured MCP server."""
    tools = await build_client(settings).get_tools(server_name=_SERVER)
    for tool in tools:
        if tool.name == _SEARCH_TOOL:
            return tool
    raise LookupError(
        f"MCP server {settings.agent_search_mcp_url!r} exposes no {_SEARCH_TOOL!r} tool "
        f"(saw: {sorted(t.name for t in tools)})"
    )
