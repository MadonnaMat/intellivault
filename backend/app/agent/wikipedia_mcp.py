"""The Wikipedia MCP: authoritative entity summaries + related topics.

The ``lookup`` node uses these to fill entity ``attributes`` with a canonical
description and to propose relationships from an article's link graph — a much
higher-signal source for a knowledge graph than arbitrary web pages.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool

from app.agent.mcp_client import index_by_name, load_mcp_tools
from app.config import Settings

_SERVER = "wikipedia"
# The wikipedia-mcp server exposes each tool bare and ``wikipedia_``-prefixed;
# index_by_name keeps the bare alias.
WANTED = ("search_wikipedia", "get_summary", "get_related_topics")


async def load_wikipedia_tools(settings: Settings) -> dict[str, BaseTool]:
    tools = index_by_name(await load_mcp_tools(settings.agent_wikipedia_mcp_url, _SERVER))
    missing = [name for name in WANTED if name not in tools]
    if missing:
        raise LookupError(
            f"MCP server {settings.agent_wikipedia_mcp_url!r} is missing tools {missing} "
            f"(saw: {sorted(tools)})"
        )
    return {name: tools[name] for name in WANTED}
