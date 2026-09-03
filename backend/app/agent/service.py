"""Postgres access for ``agent_runs`` + the enqueue seam.

The three read/create functions back the HTTP routes (tenant-scoped by
``user_id``); the rest are the write path the taskiq worker drives as a
LangGraph run progresses. Multi-line SQL lives in ``app/agent/sql/``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import HTTPException, status
from pydantic import BaseModel

from app.agent.schemas import AgentRun, AgentRunCreate, AgentRunResult, AgentRunSummary, Plan
from app.agent.statements import sql

_NOT_FOUND = status.HTTP_404_NOT_FOUND


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


async def list_runs(pool: asyncpg.Pool, user_id: UUID) -> list[AgentRunSummary]:
    rows = await pool.fetch(sql("list_runs"), user_id)
    return [_summary(row) for row in rows]


async def enqueue_run(run_id: UUID) -> None:
    """Hand the run to the taskiq worker. Imported lazily so the gateway's import
    path never pulls in langgraph."""
    from app.agent.tasks import run_agent

    await run_agent.kiq(str(run_id))


# --- worker write path ------------------------------------------------------


async def get_run_internal(pool: asyncpg.Pool, run_id: UUID) -> AgentRunMeta:
    row = await pool.fetchrow(sql("get_run_internal"), run_id)
    if row is None:
        raise LookupError(f"agent_run {run_id} not found")
    return AgentRunMeta(
        id=row["id"], owner_id=str(row["user_id"]), topic=row["topic"], status=row["status"]
    )


async def mark_running(pool: asyncpg.Pool, run_id: UUID) -> None:
    await pool.execute(sql("mark_running"), run_id)


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
