"""The LangGraph state shape, in its own module so nodes + graph can share it
without a circular import.
"""

from __future__ import annotations

from typing import TypedDict

from app.agent.fetch import FetchedDoc
from app.agent.schemas import GraphDigest, Plan, SearchHit, StructuredResult


class AgentState(TypedDict):
    # inputs — set by initial_state, never mutated
    topic: str
    owner_id: str
    run_id: str
    # progressively filled
    plan: Plan | None
    existing_graph: GraphDigest | None
    search_hits: list[SearchHit]
    documents: list[FetchedDoc]
    analysis: str | None
    structured: StructuredResult | None
    committed_entity_ids: list[str]
    committed_relationship_ids: list[str]
    skipped: list[str]


def initial_state(topic: str, owner_id: str, run_id: str) -> AgentState:
    return AgentState(
        topic=topic,
        owner_id=owner_id,
        run_id=run_id,
        plan=None,
        existing_graph=None,
        search_hits=[],
        documents=[],
        analysis=None,
        structured=None,
        committed_entity_ids=[],
        committed_relationship_ids=[],
        skipped=[],
    )
