"""Agent-loop routes: start a research run, list runs, poll one run.

Thin HTTP shell over :mod:`app.agent.service`. Every route is tenant-scoped —
``user.id`` is baked into the SQL ``WHERE`` — and the actual work happens in the
separate taskiq worker (:mod:`app.agent.tasks`), so ``POST`` returns 202.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, status

from app.agent import service
from app.agent.schemas import AgentRun, AgentRunCreate, AgentRunReview, AgentRunSummary
from app.auth.dependencies import current_user
from app.auth.schemas import SessionUser
from app.db import get_pool

router = APIRouter(prefix="/agent", tags=["agent"])

Pool = Annotated[asyncpg.Pool, Depends(get_pool)]
CurrentUser = Annotated[SessionUser, Depends(current_user)]


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def create_run(data: AgentRunCreate, pool: Pool, user: CurrentUser) -> AgentRun:
    run = await service.create_run(pool, user.id, data)
    await service.enqueue_run(run.id)
    return run


@router.get("/runs")
async def list_runs(pool: Pool, user: CurrentUser) -> list[AgentRunSummary]:
    return await service.list_runs(pool, user.id)


@router.get("/runs/{run_id}")
async def get_run(run_id: UUID, pool: Pool, user: CurrentUser) -> AgentRun:
    return await service.get_run(pool, user.id, run_id)


@router.post("/runs/{run_id}/review")
async def review_run(run_id: UUID, data: AgentRunReview, pool: Pool, user: CurrentUser) -> AgentRun:
    """Approve (optionally editing the drafts) or reject a run awaiting review."""
    run = await service.submit_review(pool, user.id, run_id, data)
    if data.decision == "approve":
        await service.enqueue_commit(run.id)
    return run
