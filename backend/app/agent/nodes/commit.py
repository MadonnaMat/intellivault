"""``commit`` — write the drafted entities + relationships to the graph.

Every write goes through ``app.graph.service`` with ``visibility="private"`` —
no new Cypher — so every ``owner_id`` / ``visibility`` predicate holds. The batch
is **not** atomic: ``append_committed_*`` records each write as it lands, so a
crash leaves an accurate partial record. A service 404/422 on an edge (the caller
doesn't own an endpoint) goes to ``skipped``, never fatal.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import HTTPException

from app.agent import service as agent_service
from app.agent.deps import AgentDeps
from app.agent.graph_state import AgentState
from app.agent.schemas import DraftEntity, DraftRelationship, StructuredResult
from app.graph import service as graph_service
from app.graph.schemas import EntityInput, RelationshipInput


def _resolve_ref(ref: str, id_map: dict[str, UUID]) -> UUID | None:
    if ref in id_map:
        return id_map[ref]
    try:
        return UUID(ref)
    except ValueError:
        return None


def _embed_text(draft: DraftEntity) -> str:
    text = f"{draft.name} ({draft.kind})"
    if draft.attributes:
        text += "\n" + json.dumps(draft.attributes, sort_keys=True)
    return text


async def _embed_entity(
    entity_id: UUID, draft: DraftEntity, *, state: AgentState, deps: AgentDeps, skipped: list[str]
) -> None:
    """Best-effort: an embedding failure is noted, never fatal to the commit."""
    try:
        vector = await deps.embedder.aembed_query(_embed_text(draft))
        await graph_service.set_entity_embedding(
            deps.driver, state["owner_id"], str(entity_id), vector
        )
    except Exception as exc:  # noqa: BLE001
        skipped.append(f"embed {draft.name}: {exc}")


async def _commit_entities(
    drafts: list[DraftEntity], *, state: AgentState, deps: AgentDeps
) -> tuple[dict[str, UUID], list[str], list[str]]:
    run_id = UUID(state["run_id"])
    id_map: dict[str, UUID] = {}
    committed = list(state["committed_entity_ids"])
    skipped: list[str] = []
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
        await _embed_entity(entity.id, draft, state=state, deps=deps, skipped=skipped)
    return id_map, committed, skipped


async def _commit_relationships(
    drafts: list[DraftRelationship], id_map: dict[str, UUID], *, state: AgentState, deps: AgentDeps
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
    id_map, committed_entities, entity_skipped = await _commit_entities(
        result.entities, state=state, deps=deps
    )
    committed_rels, rel_skipped = await _commit_relationships(
        result.relationships, id_map, state=state, deps=deps
    )
    return {
        "committed_entity_ids": committed_entities,
        "committed_relationship_ids": committed_rels,
        "skipped": [*state["skipped"], *entity_skipped, *rel_skipped],
    }
