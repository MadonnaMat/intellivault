"""The seven LangGraph nodes.

Each is ``async def <name>_node(state, *, deps) -> dict[str, Any]`` returning a
partial update that LangGraph shallow-merges into the state. The graph is linear
(no fan-out) so there are no reducers. Non-scalar clients ride on ``deps``, never
in state.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent import service as agent_service
from app.agent.deps import AgentDeps
from app.agent.fetch import FetchedDoc, SsrfError, fetch_text, guard_url
from app.agent.graph_state import AgentState
from app.agent.llm import StructuredOutputError, structured
from app.agent.prompts import prompt
from app.agent.schemas import (
    DigestEdge,
    DigestEntity,
    DraftEntity,
    GraphDigest,
    Plan,
    SearchHit,
    StructuredResult,
)
from app.graph import service as graph_service
from app.graph.schemas import Entity, EntityInput, RelationshipInput

_TOKEN = re.compile(r"[a-z0-9]+")

# --- plan / survey --------------------------------------------------------


async def plan_node(state: AgentState, *, deps: AgentDeps) -> dict[str, Any]:
    plan = await structured(
        deps.chat_model,
        Plan,
        [
            SystemMessage(content=prompt("plan_system")),
            HumanMessage(content=f"Topic: {state['topic']}"),
        ],
    )
    return {"plan": plan}


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if len(t) > 2}


def _relevance_tokens(state: AgentState) -> set[str]:
    plan = state["plan"]
    parts = [state["topic"], *(plan.queries if plan is not None else [])]
    return _tokens(" ".join(parts))


def _rank_entities(entities: list[Entity], tokens: set[str], limit: int) -> list[Entity]:
    """Most topic-relevant first (by name/kind token overlap), then newest."""

    def key(entity: Entity) -> tuple[int, float]:
        overlap = len(_tokens(f"{entity.name} {entity.kind}") & tokens)
        return overlap, entity.created_at.timestamp()

    return sorted(entities, key=key, reverse=True)[:limit]


async def survey_graph_node(state: AgentState, *, deps: AgentDeps) -> dict[str, Any]:
    view = await graph_service.list_graph(deps.driver, state["owner_id"])
    kept = _rank_entities(
        view.entities, _relevance_tokens(state), deps.settings.agent_survey_max_entities
    )
    kept_ids = {e.id for e in kept}
    edges = [r for r in view.relationships if r.from_id in kept_ids and r.to_id in kept_ids]
    digest = GraphDigest(
        entities=[DigestEntity(id=e.id, name=e.name, kind=e.kind) for e in kept],
        relationships=[DigestEdge(from_id=r.from_id, to_id=r.to_id, kind=r.kind) for r in edges],
    )
    skipped = list(state["skipped"])
    if len(view.entities) > len(kept):
        skipped.append(f"survey: showing {len(kept)} of {len(view.entities)} visible entities")
    return {"existing_graph": digest, "skipped": skipped}


# --- search / fetch ------------------------------------------------------


def _as_items(raw: Any) -> list[Any]:
    """Normalise the MCP search tool's output (JSON string / dict / list) to a list."""
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


# --- analyse / structure ------------------------------------------------


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(part if isinstance(part, str) else str(part) for part in content)
    return str(content)


def _format_documents(docs: list[FetchedDoc]) -> str:
    if not docs:
        return "(no sources were fetched)"
    return "\n\n".join(f"SOURCE {i} <{d.url}>\n{d.text}" for i, d in enumerate(docs, 1))


def _format_digest(digest: GraphDigest | None) -> str:
    if digest is None or not digest.entities:
        return "(the existing graph is empty)"
    return "\n".join(f"- {e.name} [{e.kind}] id={e.id}" for e in digest.entities)


async def analyze_node(state: AgentState, *, deps: AgentDeps) -> dict[str, Any]:
    user_prompt = (
        f"Topic: {state['topic']}\n\n"
        f"Existing graph:\n{_format_digest(state['existing_graph'])}\n\n"
        f"Sources:\n{_format_documents(state['documents'])}"
    )
    response = await deps.chat_model.ainvoke(
        [SystemMessage(content=prompt("analyze_system")), HumanMessage(content=user_prompt)]
    )
    return {"analysis": _text(response.content)}


def _dedupe_against_existing(
    result: StructuredResult, digest: GraphDigest | None
) -> StructuredResult:
    if digest is None or not digest.entities:
        return result
    by_key = {(e.name.lower(), e.kind.lower()): e.id for e in digest.entities}
    entities = [
        d.model_copy(update={"existing_id": by_key[(d.name.lower(), d.kind.lower())]})
        if d.existing_id is None and (d.name.lower(), d.kind.lower()) in by_key
        else d
        for d in result.entities
    ]
    return result.model_copy(update={"entities": entities})


async def structure_node(state: AgentState, *, deps: AgentDeps) -> dict[str, Any]:
    skipped = list(state["skipped"])
    user_prompt = (
        f"Topic: {state['topic']}\n\n"
        f"Existing graph:\n{_format_digest(state['existing_graph'])}\n\n"
        f"Analysis:\n{state['analysis'] or '(none)'}"
    )
    try:
        result = await structured(
            deps.chat_model,
            StructuredResult,
            [
                SystemMessage(content=prompt("structure_system")),
                HumanMessage(content=user_prompt),
            ],
        )
    except StructuredOutputError as exc:
        skipped.append(f"structure: {exc}")
        return {"structured": StructuredResult(), "skipped": skipped}
    return {
        "structured": _dedupe_against_existing(result, state["existing_graph"]),
        "skipped": skipped,
    }


# --- commit -------------------------------------------------------------


def _resolve_ref(ref: str, id_map: dict[str, UUID]) -> UUID | None:
    if ref in id_map:
        return id_map[ref]
    try:
        return UUID(ref)
    except ValueError:
        return None


async def _commit_entities(
    drafts: list[DraftEntity], *, state: AgentState, deps: AgentDeps
) -> tuple[dict[str, UUID], list[str]]:
    run_id = UUID(state["run_id"])
    id_map: dict[str, UUID] = {}
    committed = list(state["committed_entity_ids"])
    for draft in drafts:
        if draft.existing_id is not None:
            id_map[draft.temp_id] = draft.existing_id
            continue
        entity = await graph_service.create_entity(
            deps.driver,
            state["owner_id"],
            EntityInput(
                name=draft.name, kind=draft.kind, attributes=draft.attributes, visibility="private"
            ),
        )
        id_map[draft.temp_id] = entity.id
        committed.append(str(entity.id))
        await agent_service.append_committed_entity(deps.pool, run_id, entity.id)
    return id_map, committed


async def _commit_relationships(
    drafts: list[Any], id_map: dict[str, UUID], *, state: AgentState, deps: AgentDeps
) -> tuple[list[str], list[str]]:
    run_id = UUID(state["run_id"])
    committed = list(state["committed_relationship_ids"])
    skipped: list[str] = []
    for edge in drafts:
        source, target = _resolve_ref(edge.from_ref, id_map), _resolve_ref(edge.to_ref, id_map)
        if source is None or target is None:
            skipped.append(f"relationship {edge.from_ref}->{edge.to_ref}: unresolved endpoint")
            continue
        try:
            rel = await graph_service.create_relationship(
                deps.driver,
                state["owner_id"],
                RelationshipInput(
                    from_id=source, to_id=target, kind=edge.kind, visibility="private"
                ),
            )
        except HTTPException as exc:
            skipped.append(f"relationship {edge.from_ref}->{edge.to_ref}: {exc.detail}")
            continue
        committed.append(str(rel.id))
        await agent_service.append_committed_relationship(deps.pool, run_id, rel.id)
    return committed, skipped


async def commit_node(state: AgentState, *, deps: AgentDeps) -> dict[str, Any]:
    result = state["structured"] or StructuredResult()
    id_map, committed_entities = await _commit_entities(result.entities, state=state, deps=deps)
    committed_rels, rel_skipped = await _commit_relationships(
        result.relationships, id_map, state=state, deps=deps
    )
    return {
        "committed_entity_ids": committed_entities,
        "committed_relationship_ids": committed_rels,
        "skipped": [*state["skipped"], *rel_skipped],
    }
