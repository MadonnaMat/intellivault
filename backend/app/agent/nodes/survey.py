"""``survey_graph`` — a bounded digest of the caller's visible graph for context.

Vector-search the topic against embedded entities; fall back to lexical ranking
(token overlap, then recency) when there are no embeddings / Ollama is down.
"""

from __future__ import annotations

from typing import Any

from app.agent.deps import AgentDeps
from app.agent.graph_state import AgentState
from app.agent.nodes._common import tokens
from app.agent.schemas import DigestEdge, DigestEntity, GraphDigest
from app.graph import service as graph_service
from app.graph.schemas import Entity


def _relevance_tokens(state: AgentState) -> set[str]:
    plan = state["plan"]
    parts = [state["topic"], *(plan.queries if plan is not None else [])]
    return tokens(" ".join(parts))


def _rank_entities(entities: list[Entity], topic_tokens: set[str], limit: int) -> list[Entity]:
    def key(entity: Entity) -> tuple[int, float]:
        overlap = len(tokens(f"{entity.name} {entity.kind}") & topic_tokens)
        return overlap, entity.created_at.timestamp()

    return sorted(entities, key=key, reverse=True)[:limit]


def _survey_query_text(state: AgentState) -> str:
    plan = state["plan"]
    return " ".join([state["topic"], *(plan.queries if plan is not None else [])])


async def _vector_survey(state: AgentState, deps: AgentDeps, limit: int) -> list[Entity]:
    try:
        vector = await deps.embedder.aembed_query(_survey_query_text(state))
        return await graph_service.search_entities_by_vector(
            deps.driver, state["owner_id"], vector, limit
        )
    except Exception:  # noqa: BLE001 - fall back to the lexical ranking
        return []


async def survey_graph_node(state: AgentState, *, deps: AgentDeps) -> dict[str, Any]:
    limit = deps.settings.agent_survey_max_entities
    owner_id = state["owner_id"]
    skipped = list(state["skipped"])

    hits = await _vector_survey(state, deps, limit)
    if hits:
        # The vector index already bounded the read — just fetch the edges among
        # the hits, not the whole visible graph.
        kept = hits
        rels = await graph_service.list_visible_relationships_among(
            deps.driver, owner_id, [str(e.id) for e in kept]
        )
        if len(kept) >= limit:
            skipped.append(f"survey: {limit} nearest entities (there may be more)")
    else:
        # No embeddings / Ollama down — fall back to lexical ranking over the graph.
        view = await graph_service.list_graph(deps.driver, owner_id)
        kept = _rank_entities(view.entities, _relevance_tokens(state), limit)
        rels = view.relationships
        if len(view.entities) > len(kept):
            skipped.append(f"survey: showing {len(kept)} of {len(view.entities)} visible entities")

    kept_ids = {e.id for e in kept}
    edges = [r for r in rels if r.from_id in kept_ids and r.to_id in kept_ids]
    digest = GraphDigest(
        entities=[DigestEntity(id=e.id, name=e.name, kind=e.kind) for e in kept],
        relationships=[DigestEdge(from_id=r.from_id, to_id=r.to_id, kind=r.kind) for r in edges],
    )
    return {"existing_graph": digest, "skipped": skipped}
