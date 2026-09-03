"""The web-search MCP: load the SearXNG ``search`` tool over streamable HTTP.

Named ``search_mcp`` (not just ``mcp``) so a non-search MCP server (see
``wikipedia_mcp``) gets its own module + settings rather than overloading this.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool

from app.agent.mcp_client import load_mcp_tools
from app.config import Settings

_SERVER = "searxng"
_SEARCH_TOOL = "search"


async def load_search_tool(settings: Settings) -> BaseTool:
    """Resolve the ``search`` tool exposed by the configured web-search MCP server."""
    tools = await load_mcp_tools(settings.agent_search_mcp_url, _SERVER)
    for tool in tools:
        if tool.name == _SEARCH_TOOL:
            return tool
    raise LookupError(
        f"MCP server {settings.agent_search_mcp_url!r} exposes no {_SEARCH_TOOL!r} tool "
        f"(saw: {sorted(t.name for t in tools)})"
    )
