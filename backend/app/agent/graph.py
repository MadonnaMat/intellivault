"""Assemble and drive the linear research graph.

``plan → survey_graph → search → fetch → analyze → structure → commit``.
``build_graph`` binds an ``AgentDeps`` into every node; ``run_graph`` streams
node-by-node so the task can persist progress between steps.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.deps import AgentDeps
from app.agent.graph_state import AgentState, initial_state
from app.agent.nodes import (
    analyze_node,
    commit_node,
    fetch_node,
    plan_node,
    search_node,
    structure_node,
    survey_graph_node,
)

__all__ = ["AgentState", "build_graph", "initial_state", "run_graph"]

_Node = Callable[..., Awaitable[dict[str, Any]]]

_NODES: list[tuple[str, _Node]] = [
    ("plan", plan_node),
    ("survey_graph", survey_graph_node),
    ("search", search_node),
    ("fetch", fetch_node),
    ("analyze", analyze_node),
    ("structure", structure_node),
    ("commit", commit_node),
]


def _bind(fn: _Node, deps: AgentDeps) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    async def node(state: AgentState) -> dict[str, Any]:
        return await fn(state, deps=deps)

    return node


def build_graph(deps: AgentDeps) -> CompiledStateGraph[Any, Any, Any, Any]:
    builder: StateGraph[Any, Any, Any, Any] = StateGraph(AgentState)
    for name, fn in _NODES:
        # A plain async (state) -> partial-dict callable; langgraph's add_node
        # overloads don't recognise the bare Callable form under --strict.
        builder.add_node(name, _bind(fn, deps))  # type: ignore[call-overload]
    builder.add_edge(START, _NODES[0][0])
    for (before, _), (after, _) in zip(_NODES, _NODES[1:], strict=False):
        builder.add_edge(before, after)
    builder.add_edge(_NODES[-1][0], END)
    return builder.compile()


async def run_graph(
    graph: CompiledStateGraph[Any, Any, Any, Any], state: AgentState
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Yield ``(node_name, partial_update)`` after each node runs."""
    async for step in graph.astream(state, stream_mode="updates"):
        for node_name, update in step.items():
            yield node_name, update
