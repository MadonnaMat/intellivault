"""Assemble and drive the research graph.

Mostly linear, with three points of real structure:

* ``search`` loops back through ``broaden_queries`` (bounded) when a round finds
  nothing;
* ``fetch`` fans out one ``analyze_one`` per source (``Send``) and ``synthesize``
  folds the per-source notes back in (an ``operator.add`` reducer on
  ``source_notes``);
* ``critique`` bounces a weak draft back to ``structure`` (bounded).

``build_graph`` binds an ``AgentDeps`` into every node + router; ``run_graph``
streams node-by-node so the task can persist progress between steps.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from app.agent.deps import AgentDeps
from app.agent.graph_state import AgentState, initial_state
from app.agent.nodes import (
    analyze_one_node,
    broaden_queries_node,
    commit_node,
    critique_node,
    enrich_node,
    fetch_node,
    lookup_node,
    plan_node,
    search_node,
    structure_node,
    survey_graph_node,
    synthesize_node,
)

# The nodes, in a stable order for registration. Edges (below) define the flow.

__all__ = ["AgentState", "build_graph", "initial_state", "run_graph"]

_Node = Callable[..., Awaitable[dict[str, Any]]]

_NODES: list[tuple[str, _Node]] = [
    ("plan", plan_node),
    ("survey_graph", survey_graph_node),
    ("search", search_node),
    ("broaden_queries", broaden_queries_node),
    ("fetch", fetch_node),
    ("analyze_one", analyze_one_node),
    ("synthesize", synthesize_node),
    ("structure", structure_node),
    ("critique", critique_node),
    ("lookup", lookup_node),
    ("commit", commit_node),
    ("enrich", enrich_node),
]


def _bind(fn: _Node, deps: AgentDeps) -> Callable[[Any], Awaitable[dict[str, Any]]]:
    async def node(state: Any) -> dict[str, Any]:
        return await fn(state, deps=deps)

    return node


def _route_after_search(deps: AgentDeps) -> Callable[[AgentState], str]:
    def route(state: AgentState) -> str:
        exhausted = state["search_attempts"] >= deps.settings.agent_search_retries
        return "fetch" if state["search_hits"] or exhausted else "broaden_queries"

    return route


def _fan_out_analyze(state: AgentState) -> list[Send] | str:
    docs = state["documents"]
    if not docs:
        return "synthesize"
    return [Send("analyze_one", {"topic": state["topic"], "document": doc}) for doc in docs]


def _route_after_critique(deps: AgentDeps) -> Callable[[AgentState], str]:
    def route(state: AgentState) -> str:
        exhausted = state["critique_attempts"] >= deps.settings.agent_critique_retries
        return "lookup" if state["critique"] is None or exhausted else "structure"

    return route


def build_graph(deps: AgentDeps, *, review: bool = False) -> CompiledStateGraph[Any, Any, Any, Any]:
    """The research graph. With ``review=True`` it ends at ``lookup`` — the task
    persists the drafts and stops until an approval resumes the commit phase
    (:func:`app.agent.tasks._commit_agent_run`)."""
    builder: StateGraph[Any, Any, Any, Any] = StateGraph(AgentState)
    nodes = _NODES if not review else [n for n in _NODES if n[0] not in {"commit", "enrich"}]
    for name, fn in nodes:
        builder.add_node(name, _bind(fn, deps))  # type: ignore[call-overload]

    builder.add_edge(START, "plan")
    builder.add_edge("plan", "survey_graph")
    builder.add_edge("survey_graph", "search")
    builder.add_conditional_edges("search", _route_after_search(deps), ["broaden_queries", "fetch"])
    builder.add_edge("broaden_queries", "search")
    builder.add_conditional_edges("fetch", _fan_out_analyze, ["analyze_one", "synthesize"])
    builder.add_edge("analyze_one", "synthesize")
    builder.add_edge("synthesize", "structure")
    builder.add_edge("structure", "critique")
    builder.add_conditional_edges("critique", _route_after_critique(deps), ["structure", "lookup"])
    if review:
        builder.add_edge("lookup", END)
    else:
        builder.add_edge("lookup", "commit")
        builder.add_edge("commit", "enrich")
        builder.add_edge("enrich", END)
    return builder.compile()


async def run_graph(
    graph: CompiledStateGraph[Any, Any, Any, Any], state: AgentState
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Yield ``(node_name, partial_update)`` after each node runs."""
    async for step in graph.astream(state, stream_mode="updates"):
        for node_name, update in step.items():
            # a fan-out branch (`analyze_one`) streams once per branch; a node
            # that returned nothing keys to None.
            for one in update if isinstance(update, list) else [update]:
                yield node_name, one or {}
