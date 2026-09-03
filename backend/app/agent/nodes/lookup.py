"""``lookup`` — enrich the drafted entities from Wikipedia before commit.

For each draft entity: find its article, attach the summary to ``attributes``,
and turn the article's related topics into extra draft relationships when they
match another draft entity. Best-effort per entity — a Wikipedia failure is
noted, never fatal.
"""

from __future__ import annotations

from typing import Any

from app.agent.deps import AgentDeps
from app.agent.graph_state import AgentState
from app.agent.nodes._common import call_tool, coerce_mcp
from app.agent.schemas import DraftEntity, DraftRelationship, StructuredResult
from app.agent.wikipedia_mcp import WANTED as _WIKI_TOOLS

_SUMMARY_LIMIT = 600


def _first_title(raw: Any, fallback: str) -> str:
    data = coerce_mcp(raw)
    items = data.get("results") or data.get("pages") or [] if isinstance(data, dict) else data
    if isinstance(items, list):
        for item in items:
            title = item.get("title") if isinstance(item, dict) else item
            if title:
                return str(title)
    return fallback


def _summary_text(raw: Any) -> str:
    data = coerce_mcp(raw)
    if isinstance(data, dict):
        return str(data.get("summary") or data.get("extract") or data.get("text") or "")
    return str(data or "")


def _related_names(raw: Any) -> list[str]:
    data = coerce_mcp(raw)
    values = (
        data.get("related") or data.get("topics") or data.get("links") or []
        if isinstance(data, dict)
        else data
    )
    out: list[str] = []
    for item in values if isinstance(values, list) else []:
        name = item.get("title") or item.get("name") if isinstance(item, dict) else item
        if name:
            out.append(str(name))
    return out


async def _enrich_one(
    draft: DraftEntity, by_name: dict[str, str], *, deps: AgentDeps, skipped: list[str]
) -> tuple[DraftEntity, list[DraftRelationship]]:
    tools = deps.wikipedia_tools
    timeout = deps.settings.agent_mcp_timeout
    try:
        title = _first_title(
            await call_tool(tools["search_wikipedia"], {"query": draft.name}, timeout=timeout),
            draft.name,
        )
        summary = _summary_text(
            await call_tool(tools["get_summary"], {"title": title}, timeout=timeout)
        )
        related = _related_names(
            await call_tool(tools["get_related_topics"], {"title": title}, timeout=timeout)
        )
    except Exception as exc:  # noqa: BLE001
        skipped.append(f"lookup {draft.name}: {exc}")
        return draft, []

    attrs = draft.attributes
    if summary:
        attrs = {**attrs, "wikipedia_summary": summary[:_SUMMARY_LIMIT]}
    edges = [
        DraftRelationship(from_ref=draft.temp_id, to_ref=by_name[name.lower()], kind="related_to")
        for name in related
        if name.lower() in by_name and by_name[name.lower()] != draft.temp_id
    ]
    return draft.model_copy(update={"attributes": attrs}), edges


async def lookup_node(state: AgentState, *, deps: AgentDeps) -> dict[str, Any]:
    result = state["structured"] or StructuredResult()
    if not result.entities:
        return {}
    if any(name not in deps.wikipedia_tools for name in _WIKI_TOOLS):
        return {"skipped": [*state["skipped"], "lookup: Wikipedia MCP unavailable — skipped"]}
    by_name = {e.name.lower(): e.temp_id for e in result.entities}
    skipped = list(state["skipped"])

    # Each entity is 3 sequential MCP round trips — cap the count so a huge draft
    # list can't grind for many minutes. The rest pass through un-enriched.
    cap = deps.settings.agent_lookup_max_entities
    to_enrich, rest = result.entities[:cap], result.entities[cap:]
    if rest:
        skipped.append(
            f"lookup: enriched {len(to_enrich)} of {len(result.entities)} entities (cap)"
        )

    entities: list[DraftEntity] = []
    extra: list[DraftRelationship] = []
    for draft in to_enrich:
        enriched, edges = await _enrich_one(draft, by_name, deps=deps, skipped=skipped)
        entities.append(enriched)
        extra.extend(edges)
    entities.extend(rest)

    seen = {(r.from_ref, r.to_ref, r.kind) for r in result.relationships}
    new_edges = [r for r in extra if (r.from_ref, r.to_ref, r.kind) not in seen]
    updated = result.model_copy(
        update={"entities": entities, "relationships": [*result.relationships, *new_edges]}
    )
    return {"structured": updated, "skipped": skipped}
