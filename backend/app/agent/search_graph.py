"""The ``search_knowledge_graph`` chat tool's execution, as a LangGraph.

Vector-search the caller's visible graph for the query; only when that comes
up empty, fall back to a lexical scan of the whole visible graph (mirroring
``app.agent.nodes.survey``'s bounded-digest fallback) — then fetch the edges
among whichever entities were kept. Runs in the worker process
(``app.agent.tasks.search_knowledge_graph_task``), never the gateway — the
gateway only enqueues the task and waits for its result (see
``app.chat.graph_search``), so ``tests/agent/test_imports.py`` stays green.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.deps import AgentDeps
from app.agent.nodes._common import tokens
from app.graph import service as graph_service
from app.graph.schemas import Entity, Relationship


class SearchState(TypedDict):
    owner_id: str
    query: str
    limit: int
    entities: list[Entity]
    relationships: list[Relationship]
    note: str | None


def initial_state(owner_id: str, query: str, limit: int) -> SearchState:
    return SearchState(
        owner_id=owner_id, query=query, limit=limit, entities=[], relationships=[], note=None
    )


async def _vector_search_node(state: SearchState, *, deps: AgentDeps) -> dict[str, Any]:
    try:
        vector = await deps.embedder.aembed_query(state["query"])
        hits = await graph_service.search_entities_by_vector(
            deps.driver, state["owner_id"], vector, state["limit"]
        )
    except Exception:  # noqa: BLE001 - fall back to the lexical node
        return {"entities": []}
    return {"entities": hits}


def _route_after_vector_search(state: SearchState) -> str:
    return "fetch_edges" if state["entities"] else "lexical_fallback"


def _rank(entities: list[Entity], query_tokens: set[str]) -> list[tuple[int, Entity]]:
    def overlap(entity: Entity) -> int:
        return len(tokens(f"{entity.name} {entity.kind}") & query_tokens)

    return sorted(((overlap(e), e) for e in entities), key=lambda pair: pair[0], reverse=True)


async def _lexical_fallback_node(state: SearchState, *, deps: AgentDeps) -> dict[str, Any]:
    """No embeddings / Ollama down / nothing vector-close — rank the whole
    visible graph by token overlap with the query, keeping only entities that
    actually share a token (unlike survey's digest, an empty-overlap entity
    isn't useful context for "what do we know about X")."""
    view = await graph_service.list_graph(deps.driver, state["owner_id"])
    ranked = _rank(view.entities, tokens(state["query"]))
    kept = [entity for score, entity in ranked[: state["limit"]] if score > 0]
    note = None if kept else "no matching entities found in the knowledge graph"
    return {"entities": kept, "note": note}


async def _fetch_edges_node(state: SearchState, *, deps: AgentDeps) -> dict[str, Any]:
    if not state["entities"]:
        return {"relationships": []}
    ids = [str(e.id) for e in state["entities"]]
    relationships = await graph_service.list_visible_relationships_among(
        deps.driver, state["owner_id"], ids
    )
    return {"relationships": relationships}


_Node = Callable[..., Awaitable[dict[str, Any]]]


def _bind(fn: _Node, deps: AgentDeps) -> Callable[[SearchState], Awaitable[dict[str, Any]]]:
    async def node(state: SearchState) -> dict[str, Any]:
        return await fn(state, deps=deps)

    return node


def build_search_graph(deps: AgentDeps) -> CompiledStateGraph[Any, Any, Any, Any]:
    builder: StateGraph[Any, Any, Any, Any] = StateGraph(SearchState)
    builder.add_node("vector_search", _bind(_vector_search_node, deps))  # type: ignore[call-overload]
    builder.add_node("lexical_fallback", _bind(_lexical_fallback_node, deps))  # type: ignore[call-overload]
    builder.add_node("fetch_edges", _bind(_fetch_edges_node, deps))  # type: ignore[call-overload]

    builder.set_entry_point("vector_search")
    builder.add_conditional_edges(
        "vector_search",
        _route_after_vector_search,
        {"fetch_edges": "fetch_edges", "lexical_fallback": "lexical_fallback"},
    )
    builder.add_edge("lexical_fallback", "fetch_edges")
    builder.add_edge("fetch_edges", END)
    return builder.compile()
