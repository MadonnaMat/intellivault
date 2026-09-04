"""Postgres access for ``agent_runs`` + the enqueue seam.

The three read/create functions back the HTTP routes (tenant-scoped by
``user_id``); the rest are the write path the taskiq worker drives as a
LangGraph run progresses. Multi-line SQL lives in ``app/agent/sql/``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import HTTPException, status
from pydantic import BaseModel

from app.agent.schemas import (
    AgentRun,
    AgentRunCreate,
    AgentRunResult,
    AgentRunReview,
    AgentRunSummary,
    Plan,
    StructuredResult,
)
from app.agent.statements import sql
from app.streaming import format_sse, format_sse_comment

_NOT_FOUND = status.HTTP_404_NOT_FOUND
_CONFLICT = status.HTTP_409_CONFLICT

# awaiting_review is terminal-for-the-stream: a stable state needing a UI
# decision, not an in-progress one. The frontend has the full AgentRun
# (including `pending`) from that final event and can render review controls
# without staying subscribed.
_STREAM_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "awaiting_review"}
_POLL_INTERVAL_SECONDS = 1.0
_HEARTBEAT_INTERVAL_SECONDS = 15.0


@dataclass(frozen=True, slots=True)
class AgentRunMeta:
    """What the worker needs to run a job: the topic and whose graph to write to."""

    id: UUID
    owner_id: str
    topic: str
    status: str


def _load[TModel: BaseModel](raw: Any, model: type[TModel]) -> TModel | None:
    """Parse a JSONB column (asyncpg hands it back as ``str``; tests pass a dict)."""
    if raw is None:
        return None
    if isinstance(raw, str):
        return model.model_validate_json(raw)
    return model.model_validate(raw)


def _summary(row: asyncpg.Record) -> AgentRunSummary:
    return AgentRunSummary(
        id=row["id"],
        topic=row["topic"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _run(row: asyncpg.Record) -> AgentRun:
    return AgentRun(
        id=row["id"],
        topic=row["topic"],
        status=row["status"],
        current_node=row["current_node"],
        plan=_load(row["plan"], Plan),
        result=_load(row["result"], AgentRunResult),
        pending=_load(row["pending"], StructuredResult),
        committed_entity_ids=list(row["committed_entity_ids"]),
        committed_relationship_ids=list(row["committed_relationship_ids"]),
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# --- HTTP-facing (tenant-scoped) ---------------------------------------------


async def create_run(pool: asyncpg.Pool, user_id: UUID, data: AgentRunCreate) -> AgentRun:
    row = await pool.fetchrow(sql("insert_run"), user_id, data.topic)
    assert row is not None  # INSERT ... RETURNING always yields a row
    return _run(row)


async def get_run(pool: asyncpg.Pool, user_id: UUID, run_id: UUID) -> AgentRun:
    row = await pool.fetchrow(sql("get_run"), run_id, user_id)
    if row is None:
        raise HTTPException(_NOT_FOUND, "Run not found")
    return _run(row)


async def stream_run(pool: asyncpg.Pool, user_id: UUID, run_id: UUID) -> AsyncIterator[bytes]:
    """Poll ``agent_runs`` and yield an SSE ``status`` event on every change,
    stopping once the run reaches a terminal status.

    Callers must confirm the run exists (``get_run``) *before* constructing a
    ``StreamingResponse`` around this generator: an ASGI streaming response
    commits to its status code the moment streaming starts, so a 404 raised
    from in here — on a run deleted mid-stream, say — couldn't change it.
    """
    last_updated_at = None
    last_heartbeat = asyncio.get_running_loop().time()
    while True:
        run = await get_run(pool, user_id, run_id)
        if run.updated_at != last_updated_at:
            last_updated_at = run.updated_at
            yield format_sse("status", run.model_dump(mode="json"))
            last_heartbeat = asyncio.get_running_loop().time()
        if run.status in _STREAM_TERMINAL_STATUSES:
            return
        now = asyncio.get_running_loop().time()
        if now - last_heartbeat >= _HEARTBEAT_INTERVAL_SECONDS:
            yield format_sse_comment("keep-alive")
            last_heartbeat = now
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)


async def list_runs(pool: asyncpg.Pool, user_id: UUID) -> list[AgentRunSummary]:
    rows = await pool.fetch(sql("list_runs"), user_id)
    return [_summary(row) for row in rows]


async def submit_review(
    pool: asyncpg.Pool, user_id: UUID, run_id: UUID, review: AgentRunReview
) -> AgentRun:
    """Approve (optionally with edits) or reject a run that's ``awaiting_review``."""
    row = await pool.fetchrow(sql("get_run"), run_id, user_id)
    if row is None:
        raise HTTPException(_NOT_FOUND, "Run not found")
    if row["status"] != "awaiting_review":
        raise HTTPException(_CONFLICT, f"Run is {row['status']}, not awaiting review")

    if review.decision == "reject":
        updated = await pool.fetchrow(sql("mark_cancelled"), run_id)
    else:
        pending = _load(row["pending"], StructuredResult) or StructuredResult()
        if review.entities is not None:
            pending = pending.model_copy(update={"entities": review.entities})
        if review.relationships is not None:
            pending = pending.model_copy(update={"relationships": review.relationships})
        updated = await pool.fetchrow(sql("approve_review"), run_id, pending.model_dump_json())
    assert updated is not None
    return _run(updated)


async def enqueue_run(run_id: UUID) -> None:
    """Hand the run to the taskiq worker. Imported lazily so the gateway's import
    path never pulls in langgraph."""
    from app.agent.tasks import run_agent

    await run_agent.kiq(str(run_id))


async def enqueue_commit(run_id: UUID) -> None:
    """Hand an approved run to the worker for its commit phase (lazy import)."""
    from app.agent.tasks import commit_agent_run

    await commit_agent_run.kiq(str(run_id))


# --- worker write path ------------------------------------------------------


async def get_run_internal(pool: asyncpg.Pool, run_id: UUID) -> AgentRunMeta:
    row = await pool.fetchrow(sql("get_run_internal"), run_id)
    if row is None:
        raise LookupError(f"agent_run {run_id} not found")
    return AgentRunMeta(
        id=row["id"], owner_id=str(row["user_id"]), topic=row["topic"], status=row["status"]
    )


def _load_urls(raw: Any) -> list[str]:
    """Parse the ``source_urls`` JSONB column (asyncpg hands it back as ``str``;
    tests pass a list directly)."""
    if raw is None:
        return []
    return json.loads(raw) if isinstance(raw, str) else list(raw)


@dataclass(frozen=True, slots=True)
class ParkedRun:
    """What an approved run resumes from: the drafts to commit, the research
    phase's partial result (analysis + skipped notes), and the URLs it
    fetched (so the commit phase can re-attach sources)."""

    drafts: StructuredResult
    partial: AgentRunResult | None
    source_urls: list[str]


async def load_parked(pool: asyncpg.Pool, run_id: UUID) -> ParkedRun:
    row = await pool.fetchrow(sql("get_pending"), run_id)
    if row is None:
        return ParkedRun(StructuredResult(), None, [])
    return ParkedRun(
        drafts=_load(row["pending"], StructuredResult) or StructuredResult(),
        partial=_load(row["result"], AgentRunResult),
        source_urls=_load_urls(row["source_urls"]),
    )


async def mark_running(pool: asyncpg.Pool, run_id: UUID) -> None:
    await pool.execute(sql("mark_running"), run_id)


async def mark_awaiting_review(
    pool: asyncpg.Pool,
    run_id: UUID,
    pending: StructuredResult,
    partial: AgentRunResult,
    source_urls: list[str],
) -> None:
    await pool.execute(
        sql("mark_awaiting_review"),
        run_id,
        pending.model_dump_json(),
        partial.model_dump_json(),
        json.dumps(source_urls),
    )


async def record_node(
    pool: asyncpg.Pool, run_id: UUID, node: str, *, plan: Plan | None = None
) -> None:
    await pool.execute(
        sql("record_node"), run_id, node, plan.model_dump_json() if plan is not None else None
    )


async def append_committed_entity(pool: asyncpg.Pool, run_id: UUID, entity_id: UUID) -> None:
    await pool.execute(sql("append_committed_entity"), run_id, entity_id)


async def append_committed_relationship(
    pool: asyncpg.Pool, run_id: UUID, relationship_id: UUID
) -> None:
    await pool.execute(sql("append_committed_relationship"), run_id, relationship_id)


async def mark_succeeded(
    pool: asyncpg.Pool,
    run_id: UUID,
    result: AgentRunResult,
    entity_ids: Iterable[UUID],
    relationship_ids: Iterable[UUID],
) -> None:
    await pool.execute(
        sql("mark_succeeded"),
        run_id,
        result.model_dump_json(),
        list(entity_ids),
        list(relationship_ids),
    )


async def mark_failed(
    pool: asyncpg.Pool,
    run_id: UUID,
    error: str,
    entity_ids: Iterable[UUID],
    relationship_ids: Iterable[UUID],
) -> None:
    await pool.execute(sql("mark_failed"), run_id, error, list(entity_ids), list(relationship_ids))
