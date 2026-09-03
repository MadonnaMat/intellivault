"""Request/response models for the agent-loop routes.

The worker-internal models the LangGraph nodes pass around (search hits, fetched
docs, the structured-output drafts) live in :mod:`app.agent.graph`; only what
crosses the HTTP boundary is here. ``owner_id`` on the wire is ``str(user.id)``,
matching :mod:`app.graph`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

AgentRunStatus = Literal["queued", "running", "succeeded", "failed"]

Topic = Annotated[str, Field(min_length=3, max_length=500)]
_Name = Annotated[str, Field(min_length=1, max_length=200)]
_Kind = Annotated[str, Field(min_length=1, max_length=100)]


class AgentRunCreate(BaseModel):
    """Kick off a run: a research topic the agent turns into private graph nodes."""

    topic: Topic


class Plan(BaseModel):
    """The plan node's output — a short framing plus the web-search queries."""

    summary: str
    queries: Annotated[list[str], Field(min_length=1, max_length=8)]


# --- worker-internal models (LangGraph state; not on any route) ---------------


class SearchHit(BaseModel):
    """One web-search result from the SearXNG MCP tool."""

    url: str
    title: str = ""
    snippet: str = ""


class DigestEntity(BaseModel):
    id: UUID
    name: str
    kind: str


class DigestEdge(BaseModel):
    from_id: UUID
    to_id: UUID
    kind: str


class GraphDigest(BaseModel):
    """A compact view of the caller's currently-visible graph, for the LLM."""

    entities: list[DigestEntity] = Field(default_factory=list)
    relationships: list[DigestEdge] = Field(default_factory=list)


class DraftEntity(BaseModel):
    """A structure-node candidate. ``existing_id`` set ⇒ link, don't create."""

    temp_id: str
    name: _Name
    kind: _Kind
    attributes: dict[str, Any] = Field(default_factory=dict)
    existing_id: UUID | None = None


class DraftRelationship(BaseModel):
    """An edge between two drafts (``from_ref``/``to_ref`` = a temp_id or a UUID)."""

    from_ref: str
    to_ref: str
    kind: _Kind


class StructuredResult(BaseModel):
    entities: list[DraftEntity] = Field(default_factory=list)
    relationships: list[DraftRelationship] = Field(default_factory=list)


# --- run record --------------------------------------------------------------


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
