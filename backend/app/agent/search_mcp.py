"""The web-search MCP: load the SearXNG web-search tool over streamable HTTP.

Named ``search_mcp`` (not just ``mcp``) so a non-search MCP server (see
``wikipedia_mcp``) gets its own module + settings rather than overloading this.
"""

from __future__ import annotations

import logging

from langchain_core.tools import BaseTool

from app.agent.mcp_client import index_by_name, load_mcp_tools
from app.config import Settings

logger = logging.getLogger(__name__)

_SERVER = "searxng"
# The tool's name has drifted across the image's releases — try each. The bare
# aliases come from index_by_name(strip_prefix=...).
_SEARCH_TOOLS = ("searxng_web_search", "web_search", "search")


async def load_search_tool(settings: Settings) -> BaseTool | None:
    """The web-search tool the configured MCP server exposes, or ``None``.

    ``None`` (not an exception): a missing tool disables the ``search`` node for
    that run rather than crash-looping the worker at ``WORKER_STARTUP``.
    """
    tools = index_by_name(
        await load_mcp_tools(settings.agent_search_mcp_url, _SERVER), strip_prefix=_SERVER
    )
    for name in _SEARCH_TOOLS:
        if name in tools:
            return tools[name]
    logger.warning(
        "search MCP %s exposes no web-search tool (saw: %s) — the search step is disabled",
        settings.agent_search_mcp_url,
        sorted(tools),
    )
    return None
