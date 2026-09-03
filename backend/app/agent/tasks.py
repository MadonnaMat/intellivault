"""The agent-run tasks: stream the LangGraph and persist progress to agent_runs.

``run_agent`` runs the research graph (and, when review isn't required, commits).
``commit_agent_run`` is the second phase — it runs after an approval and commits
the parked drafts. ``_*`` are the real logic, unit-tested with a fake WorkerInfra.
"""

from __future__ import annotations

from uuid import UUID

from app.agent import service
from app.agent.broker import broker
from app.agent.deps import AgentDeps, WorkerInfra
from app.agent.graph import build_graph, initial_state, run_graph
from app.agent.graph_state import AgentState
from app.agent.nodes import commit_node, enrich_node
from app.agent.schemas import AgentRunResult, StructuredResult


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


async def _finish_succeeded(pool: object, rid: UUID, state: AgentState) -> None:
    entities, relationships = _committed(state)
    await service.mark_succeeded(pool, rid, _result(state), entities, relationships)  # type: ignore[arg-type]


async def _run_agent(run_id: str, infra: WorkerInfra) -> None:
    pool = infra.pg_pool
    rid = UUID(run_id)
    meta = await service.get_run_internal(pool, rid)
    await service.mark_running(pool, rid)

    review = infra.settings.agent_review_required
    graph = build_graph(AgentDeps.from_infra(infra), review=review)
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

    if review:
        await service.mark_awaiting_review(pool, rid, state["structured"] or StructuredResult())
        return
    await _finish_succeeded(pool, rid, state)


async def _commit_agent_run(run_id: str, infra: WorkerInfra) -> None:
    """Phase two — commit the drafts an approval unparked."""
    pool = infra.pg_pool
    rid = UUID(run_id)
    meta = await service.get_run_internal(pool, rid)
    deps = AgentDeps.from_infra(infra)
    state = initial_state(meta.topic, meta.owner_id, run_id)
    state["structured"] = await service.load_pending(pool, rid)
    try:
        state.update(await commit_node(state, deps=deps))  # type: ignore[typeddict-item]
        state.update(await enrich_node(state, deps=deps))  # type: ignore[typeddict-item]
    except Exception as exc:  # noqa: BLE001
        entities, relationships = _committed(state)
        await service.mark_failed(pool, rid, repr(exc), entities, relationships)
        raise
    await _finish_succeeded(pool, rid, state)


@broker.task
async def run_agent(run_id: str) -> None:  # pragma: no cover - thin wrapper
    await _run_agent(run_id, broker.state.infra)


@broker.task
async def commit_agent_run(run_id: str) -> None:  # pragma: no cover - thin wrapper
    await _commit_agent_run(run_id, broker.state.infra)
