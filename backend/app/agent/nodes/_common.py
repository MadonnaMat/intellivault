"""Helpers shared across the node modules — prompt formatting, tokenisation,
normalising MCP tool output.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import TYPE_CHECKING, Any

from app.agent.fetch import FetchedDoc
from app.agent.schemas import GraphDigest

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

_TOKEN = re.compile(r"[a-z0-9]+")


async def call_tool(tool: BaseTool, args: dict[str, Any], *, timeout: float) -> Any:
    """``tool.ainvoke(args)`` bounded by ``timeout`` — a hung MCP server raises
    ``TimeoutError`` instead of stalling the run. The caller decides what a
    failure means (skip note vs fatal)."""
    return await asyncio.wait_for(tool.ainvoke(args), timeout)


def coerce_mcp(raw: Any) -> Any:
    """MCP tool output -> a plain value.

    Tools return ``[{"type": "text", "text": "..."}]`` content blocks; the text
    is usually JSON. Returns the parsed dict/list, or the string if it isn't JSON.
    """
    if (
        isinstance(raw, list)
        and raw
        and all(isinstance(b, dict) and b.get("type") == "text" for b in raw)
    ):
        raw = "".join(str(b.get("text", "")) for b in raw)
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return raw
    return raw


def tokens(text: str) -> set[str]:
    """Lowercase alnum tokens longer than two chars."""
    return {t for t in _TOKEN.findall(text.lower()) if len(t) > 2}


def text_of(content: Any) -> str:
    """Flatten an LLM message ``content`` (str, or a list of parts) to a string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(part if isinstance(part, str) else str(part) for part in content)
    return str(content)


def format_documents(docs: list[FetchedDoc]) -> str:
    if not docs:
        return "(no sources were fetched)"
    return "\n\n".join(f"SOURCE {i} <{d.url}>\n{d.text}" for i, d in enumerate(docs, 1))


def format_digest(digest: GraphDigest | None) -> str:
    if digest is None or not digest.entities:
        return "(the existing graph is empty)"
    return "\n".join(f"- {e.name} [{e.kind}] id={e.id}" for e in digest.entities)
