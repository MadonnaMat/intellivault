"""Shared helper for loading tools from an MCP server over streamable HTTP.

Each ``*_mcp.py`` module wraps this for its server. ``langchain-mcp-adapters``
opens a fresh session per tool call, so a resolved tool is safe to build once
per worker and share across concurrent runs.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient


async def load_mcp_tools(url: str, server_name: str) -> list[BaseTool]:
    client = MultiServerMCPClient({server_name: {"url": url, "transport": "streamable_http"}})
    return await client.get_tools(server_name=server_name)


def index_by_name(tools: list[BaseTool]) -> dict[str, BaseTool]:
    """Tools keyed by name, preferring the un-prefixed alias when a server
    exposes both ``get_summary`` and ``wikipedia_get_summary``."""
    by_name: dict[str, BaseTool] = {}
    for tool in sorted(tools, key=lambda t: len(t.name), reverse=True):
        by_name[tool.name] = tool
    return by_name
