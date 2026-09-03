"""The agent-run task: stream the LangGraph and persist progress to agent_runs.

``_run_agent`` is the real logic (unit-tested directly with a fake ``WorkerInfra``);
``run_agent`` is the thin ``@broker.task`` wrapper the worker executes.
"""

from __future__ import annotations

from uuid import UUID

from app.agent import service
from app.agent.broker import broker
from app.agent.deps import AgentDeps, WorkerInfra
from app.agent.graph import build_graph, initial_state, run_graph
from app.agent.graph_state import AgentState
from app.agent.schemas import AgentRunResult


def _result(state: AgentState) -> AgentRunResult:
    return AgentRunResult(
        analysis=state["analysis"] or "",
        entities_created=len(state["committed_entity_ids"]),
        relationships_created=len(state["committed_relationship_ids"]),
        skipped=state["skipped"],
    )


def _committed(state: AgentState) -> tuple[list[UUID], list[UUID]]:
    return (
        [UUID(i) for i in state["committed_entity_ids"]],
        [UUID(i) for i in state["committed_relationship_ids"]],
    )


async def _run_agent(run_id: str, infra: WorkerInfra) -> None:
    pool = infra.pg_pool
    rid = UUID(run_id)
    meta = await service.get_run_internal(pool, rid)
    await service.mark_running(pool, rid)

    graph = build_graph(AgentDeps.from_infra(infra))
    state = initial_state(meta.topic, meta.owner_id, run_id)
    try:
        async for node_name, update in run_graph(graph, state):
            state.update(update)  # type: ignore[typeddict-item]
            await service.record_node(
                pool, rid, node_name, plan=state["plan"] if node_name == "plan" else None
            )
    except Exception as exc:  # noqa: BLE001 - persist the failure, then re-raise
        entities, relationships = _committed(state)
        await service.mark_failed(pool, rid, repr(exc), entities, relationships)
        raise
    entities, relationships = _committed(state)
    await service.mark_succeeded(pool, rid, _result(state), entities, relationships)


@broker.task
async def run_agent(run_id: str) -> None:  # pragma: no cover - thin wrapper
    # broker.state.infra is populated in broker._on_startup (WORKER_STARTUP).
    await _run_agent(run_id, broker.state.infra)
