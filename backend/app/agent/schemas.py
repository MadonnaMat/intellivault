"""Request/response models for the agent-loop routes.

The worker-internal models the LangGraph nodes pass around (search hits, fetched
docs, the structured-output drafts) live in :mod:`app.agent.graph`; only what
crosses the HTTP boundary is here. ``owner_id`` on the wire is ``str(user.id)``,
matching :mod:`app.graph`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

AgentRunStatus = Literal["queued", "running", "succeeded", "failed"]

Topic = Annotated[str, Field(min_length=3, max_length=500)]


class AgentRunCreate(BaseModel):
    """Kick off a run: a research topic the agent turns into private graph nodes."""

    topic: Topic


class Plan(BaseModel):
    """The plan node's output — a short framing plus the web-search queries."""

    summary: str
    queries: Annotated[list[str], Field(min_length=1, max_length=8)]


class AgentRunResult(BaseModel):
    """The finished run's summary, stored on the row and returned to the caller."""

    analysis: str
    entities_created: int
    relationships_created: int
    # Human-readable notes for every draft the run could not commit (dedupe
    # hits, unresolved edge endpoints, per-source fetch failures).
    skipped: list[str] = Field(default_factory=list)


class AgentRunSummary(BaseModel):
    """One run in the list view."""

    id: UUID
    topic: str
    status: AgentRunStatus
    created_at: datetime
    updated_at: datetime


class AgentRun(AgentRunSummary):
    """A single run in full, including in-flight progress."""

    current_node: str | None = None
    plan: Plan | None = None
    result: AgentRunResult | None = None
    committed_entity_ids: list[UUID] = Field(default_factory=list)
    committed_relationship_ids: list[UUID] = Field(default_factory=list)
    error: str | None = None
