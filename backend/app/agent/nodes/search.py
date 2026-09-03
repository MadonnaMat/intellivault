"""``search`` + ``fetch`` — find candidate sources and pull their text.

Every URL (and every redirect hop, inside ``fetch_text``) goes through the SSRF
guard before we connect. MCP tool output is normalised from whatever shape the
server returns (JSON string / dict / list / ``[{"type":"text",...}]`` blocks).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.deps import AgentDeps
from app.agent.fetch import FetchedDoc, SsrfError, fetch_text, guard_url
from app.agent.graph_state import AgentState
from app.agent.llm import structured
from app.agent.prompts import prompt
from app.agent.schemas import Plan, SearchHit


def _is_text_blocks(raw: Any) -> bool:
    return (
        isinstance(raw, list)
        and len(raw) > 0
        and all(isinstance(b, dict) and b.get("type") == "text" for b in raw)
    )


def _as_items(raw: Any, *, _unwrapped: bool = False) -> list[Any]:
    if _is_text_blocks(raw) and not _unwrapped:
        return _as_items("".join(str(b.get("text", "")) for b in raw), _unwrapped=True)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    if isinstance(raw, dict):
        raw = raw.get("results") or raw.get("items") or []
    return raw if isinstance(raw, list) else []


def _hit_from_item(item: Any) -> SearchHit | None:
    if not isinstance(item, dict):
        return None
    url = item.get("url") or item.get("link")
    if not url:
        return None
    return SearchHit(
        url=str(url),
        title=str(item.get("title") or ""),
        snippet=str(item.get("content") or item.get("snippet") or ""),
    )


def _parse_search_result(raw: Any) -> list[SearchHit]:
    return [hit for item in _as_items(raw) if (hit := _hit_from_item(item)) is not None]


async def search_node(state: AgentState, *, deps: AgentDeps) -> dict[str, Any]:
    plan = state["plan"]
    skipped = list(state["skipped"])
    if plan is None:
        return {"search_hits": [], "skipped": skipped}

    seen: set[str] = set()
    hits: list[SearchHit] = []
    limit = deps.settings.agent_max_sources
    for query in plan.queries:
        raw = await deps.search_tool.ainvoke({"query": query})
        for hit in _parse_search_result(raw):
            if hit.url in seen or len(hits) >= limit:
                continue
            seen.add(hit.url)
            try:
                await guard_url(hit.url)
            except SsrfError as exc:
                skipped.append(f"search: {hit.url} ({exc})")
                continue
            hits.append(hit)
    return {"search_hits": hits, "skipped": skipped}


async def broaden_queries_node(state: AgentState, *, deps: AgentDeps) -> dict[str, Any]:
    """A search round found nothing — ask for broader queries and try again."""
    tried = state["plan"].queries if state["plan"] is not None else []
    revised = await structured(
        deps.chat_model,
        Plan,
        [
            SystemMessage(content=prompt("broaden_system")),
            HumanMessage(
                content=f"Topic: {state['topic']}\n\nQueries that failed:\n" + "\n".join(tried)
            ),
        ],
    )
    plan = (
        revised
        if state["plan"] is None
        else state["plan"].model_copy(update={"queries": revised.queries})
    )
    return {
        "plan": plan,
        "search_attempts": state["search_attempts"] + 1,
        "skipped": [
            *state["skipped"],
            f"search: round {state['search_attempts'] + 1} — broadened queries",
        ],
    }


async def fetch_node(state: AgentState, *, deps: AgentDeps) -> dict[str, Any]:
    hits = state["search_hits"]
    results = await asyncio.gather(
        *(fetch_text(deps.http_client, hit.url, deps.settings) for hit in hits),
        return_exceptions=True,
    )
    docs: list[FetchedDoc] = []
    skipped = list(state["skipped"])
    for hit, result in zip(hits, results, strict=True):
        if isinstance(result, FetchedDoc):
            docs.append(result)
        else:
            skipped.append(f"fetch: {hit.url} ({result})")
    return {"documents": docs, "skipped": skipped}
