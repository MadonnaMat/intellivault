"""The agent-run tasks: stream the LangGraph and persist progress to agent_runs.

``run_agent`` runs the research graph (and, when review isn't required, commits).
``commit_agent_run`` is the second phase — it runs after an approval and commits
the parked drafts. ``search_knowledge_graph_task`` runs the small bounded search
graph for the chat tool of the same name and returns its result directly (no
``agent_runs`` row — ``app.chat.graph_search`` enqueues it and awaits the result
via taskiq's result backend). ``_*`` are the real logic, unit-tested with a fake
WorkerInfra.

langgraph / langchain / the node modules are imported *inside* the task bodies,
never at module load: ``service.enqueue_run`` imports this module on the gateway
to reach ``run_agent.kiq``, and that path must stay langgraph-free
(``tests/agent/test_imports.py``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any
from uuid import UUID

import asyncpg

from app.agent import service
from app.agent.broker import broker
from app.agent.fetch import FetchedDoc
from app.agent.graph_state import AgentState, initial_state
from app.agent.schemas import AgentRunResult, StructuredResult

if TYPE_CHECKING:
    from app.agent.deps import WorkerInfra


async def _guarded(
    pool: asyncpg.Pool, rid: UUID, state: AgentState, body: Awaitable[None], limit: float
) -> None:
    """Run ``body`` under an overall deadline; on any failure persist it (a
    timeout as a clear message) and re-raise so taskiq records the error."""
    try:
        await asyncio.wait_for(body, limit)
    except TimeoutError:
        entities, relationships = _committed(state)
        await service.mark_failed(
            pool, rid, f"run exceeded the {limit:g}s deadline", entities, relationships
        )
        raise
    except Exception as exc:  # noqa: BLE001 - persist the failure, then re-raise
        entities, relationships = _committed(state)
        await service.mark_failed(pool, rid, repr(exc), entities, relationships)
        raise


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
    from app.agent.deps import AgentDeps
    from app.agent.graph import build_graph, run_graph

    pool = infra.pg_pool
    rid = UUID(run_id)
    meta = await service.get_run_internal(pool, rid)
    await service.mark_running(pool, rid)

    review = infra.settings.agent_review_required
    graph = build_graph(AgentDeps.from_infra(infra), review=review)
    state = initial_state(meta.topic, meta.owner_id, run_id)

    async def _drive() -> None:
        async for node_name, update in run_graph(graph, state):
            state.update(update)  # type: ignore[typeddict-item]
            await service.record_node(
                pool, rid, node_name, plan=state["plan"] if node_name == "plan" else None
            )

    await _guarded(pool, rid, state, _drive(), infra.settings.agent_run_timeout)

    if review:
        drafts = state["structured"] or StructuredResult()
        # park the partial result too (analysis + skipped) so the commit phase
        # can restore it — otherwise an approved run finishes with an empty
        # analysis — and the fetched URLs, so the commit phase can re-attach
        # sources (otherwise attach_sources silently never runs on this path).
        source_urls = [doc.url for doc in state["documents"]]
        await service.mark_awaiting_review(pool, rid, drafts, _result(state), source_urls)
        return
    await _finish_succeeded(pool, rid, state)


async def _commit_agent_run(run_id: str, infra: WorkerInfra) -> None:
    """Phase two — commit the drafts an approval unparked."""
    from app.agent.deps import AgentDeps
    from app.agent.nodes import commit_node, enrich_node

    pool = infra.pg_pool
    rid = UUID(run_id)
    meta = await service.get_run_internal(pool, rid)
    deps = AgentDeps.from_infra(infra)
    state = initial_state(meta.topic, meta.owner_id, run_id)
    parked = await service.load_parked(pool, rid)
    state["structured"] = parked.drafts
    if parked.partial is not None:  # restore the research phase's analysis + notes
        state["analysis"] = parked.partial.analysis
        state["skipped"] = list(parked.partial.skipped)
    # commit_node only reads .url off each document (see commit.py) — a bare
    # url is enough to restore attach_sources without re-persisting page text.
    state["documents"] = [FetchedDoc(url=u, text="") for u in parked.source_urls]

    async def _commit() -> None:
        state.update(await commit_node(state, deps=deps))  # type: ignore[typeddict-item]
        state.update(await enrich_node(state, deps=deps))  # type: ignore[typeddict-item]

    await _guarded(pool, rid, state, _commit(), infra.settings.agent_run_timeout)
    await _finish_succeeded(pool, rid, state)


async def _search_knowledge_graph(
    owner_id: str, query: str, limit: int, infra: WorkerInfra
) -> dict[str, Any]:
    from app.agent.deps import AgentDeps
    from app.agent.search_graph import build_search_graph, initial_state

    deps = AgentDeps.from_infra(infra)
    graph = build_search_graph(deps)
    result = await graph.ainvoke(initial_state(owner_id, query, limit))
    return {
        "entities": [e.model_dump(mode="json") for e in result["entities"]],
        "relationships": [r.model_dump(mode="json") for r in result["relationships"]],
        "note": result.get("note"),
    }


@broker.task
async def run_agent(run_id: str) -> None:  # pragma: no cover - thin wrapper
    await _run_agent(run_id, broker.state.infra)


@broker.task
async def commit_agent_run(run_id: str) -> None:  # pragma: no cover - thin wrapper
    await _commit_agent_run(run_id, broker.state.infra)


@broker.task
async def search_knowledge_graph_task(  # pragma: no cover - thin wrapper
    owner_id: str, query: str, limit: int
) -> dict[str, Any]:
    return await _search_knowledge_graph(owner_id, query, limit, broker.state.infra)
