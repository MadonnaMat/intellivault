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


def index_by_name(tools: list[BaseTool], *, strip_prefix: str | None = None) -> dict[str, BaseTool]:
    """Tools keyed by name. With ``strip_prefix``, a ``"{prefix}_<name>"`` tool is
    *also* reachable under the bare ``<name>`` (a real bare tool always wins)."""
    by_name: dict[str, BaseTool] = {tool.name: tool for tool in tools}
    if strip_prefix:
        pfx = f"{strip_prefix}_"
        for tool in tools:
            if tool.name.startswith(pfx):
                by_name.setdefault(tool.name.removeprefix(pfx), tool)
    return by_name
