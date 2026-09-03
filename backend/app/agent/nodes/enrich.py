"""``enrich`` — after commit, link the new entities into the existing graph.

For each freshly committed entity, vector-search the caller's other entities and
ask the LLM which (if any) it should connect to. Turns isolated new sub-graphs
into a connected whole over time. Skips entirely when there was nothing else in
the graph, and is best-effort — a failure here never fails the run.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent import service as agent_service
from app.agent.deps import AgentDeps
from app.agent.graph_state import AgentState
from app.agent.llm import StructuredOutputError, structured
from app.agent.prompts import prompt
from app.agent.schemas import DigestEntity, EnrichLinks
from app.graph import service as graph_service
from app.graph.schemas import RelationshipInput

_NEIGHBOURS = 5


async def _links_for(
    entity: DigestEntity, *, state: AgentState, deps: AgentDeps, own_ids: set[str]
) -> list[tuple[str, str]]:
    try:
        vector = await deps.embedder.aembed_query(f"{entity.name} ({entity.kind})")
        near = await graph_service.search_entities_by_vector(
            deps.driver, state["owner_id"], vector, _NEIGHBOURS + len(own_ids)
        )
    except Exception:  # noqa: BLE001
        return []
    candidates = [e for e in near if str(e.id) not in own_ids][:_NEIGHBOURS]
    if not candidates:
        return []
    listing = "\n".join(f"- id={e.id} {e.name} [{e.kind}]" for e in candidates)
    try:
        links = await structured(
            deps.chat_model,
            EnrichLinks,
            [
                SystemMessage(content=prompt("enrich_system")),
                HumanMessage(
                    content=f"New entity: {entity.name} [{entity.kind}] (id={entity.id})\n\n"
                    f"Existing entities:\n{listing}"
                ),
            ],
        )
    except StructuredOutputError:
        return []
    valid = {str(e.id) for e in candidates}
    return [(link.target_id, link.kind) for link in links.links if link.target_id in valid]


async def enrich_node(state: AgentState, *, deps: AgentDeps) -> dict[str, Any]:
    created = state["committed_entities"]
    if not created:
        return {}
    own_ids = set(state["committed_entity_ids"])
    run_id = UUID(state["run_id"])
    committed = list(state["committed_relationship_ids"])
    skipped = list(state["skipped"])

    for entity in created:
        for target_id, kind in await _links_for(entity, state=state, deps=deps, own_ids=own_ids):
            try:
                rel = await graph_service.create_relationship(
                    deps.driver,
                    state["owner_id"],
                    RelationshipInput(
                        from_id=entity.id, to_id=UUID(target_id), kind=kind, visibility="private"
                    ),
                )
            except HTTPException as exc:
                skipped.append(f"enrich {entity.name}->{target_id}: {exc.detail}")
                continue
            committed.append(str(rel.id))
            await agent_service.append_committed_relationship(deps.pool, run_id, rel.id)

    return {"committed_relationship_ids": committed, "skipped": skipped}
