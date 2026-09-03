"""The Wikipedia MCP: authoritative entity summaries + related topics.

The ``lookup`` node uses these to fill entity ``attributes`` with a canonical
description and to propose relationships from an article's link graph — a much
higher-signal source for a knowledge graph than arbitrary web pages.
"""

from __future__ import annotations

import logging

from langchain_core.tools import BaseTool

from app.agent.mcp_client import index_by_name, load_mcp_tools
from app.config import Settings

logger = logging.getLogger(__name__)

_SERVER = "wikipedia"
# The wikipedia-mcp server exposes each tool bare, some also ``wikipedia_``-prefixed;
# strip_prefix lets us reach either under the bare name.
WANTED = ("search_wikipedia", "get_summary", "get_related_topics")


async def load_wikipedia_tools(settings: Settings) -> dict[str, BaseTool]:
    """The WANTED tools that the server actually exposes.

    A missing tool is logged, not raised: the ``lookup`` node is best-effort and
    disables itself when the set is incomplete — a wedged MCP image must not
    crash-loop the worker at startup.
    """
    tools = index_by_name(
        await load_mcp_tools(settings.agent_wikipedia_mcp_url, _SERVER), strip_prefix=_SERVER
    )
    resolved = {name: tools[name] for name in WANTED if name in tools}
    if missing := [name for name in WANTED if name not in tools]:
        logger.warning(
            "wikipedia MCP %s is missing tools %s (saw: %s) — the lookup step is disabled",
            settings.agent_wikipedia_mcp_url,
            missing,
            sorted(tools),
        )
    return resolved
