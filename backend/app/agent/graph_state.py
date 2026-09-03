"""The LangGraph state shape, in its own module so nodes + graph can share it
without a circular import.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from app.agent.fetch import FetchedDoc
from app.agent.schemas import DigestEntity, GraphDigest, Plan, SearchHit, StructuredResult


class AgentState(TypedDict):
    # inputs — set by initial_state, never mutated
    topic: str
    owner_id: str
    run_id: str
    # progressively filled
    plan: Plan | None
    existing_graph: GraphDigest | None
    search_hits: list[SearchHit]
    search_attempts: int  # how many times `broaden_queries` has re-queried
    documents: list[FetchedDoc]
    # each `analyze_one` fan-out branch appends one note; `synthesize` folds them
    source_notes: Annotated[list[str], operator.add]
    analysis: str | None
    structured: StructuredResult | None
    critique: str | None  # the last `critique`, carried into a structure retry
    critique_attempts: int
    committed_entity_ids: list[str]
    committed_relationship_ids: list[str]
    committed_entities: list[DigestEntity]  # the entities `commit` created, for `enrich`
    skipped: list[str]


def initial_state(topic: str, owner_id: str, run_id: str) -> AgentState:
    return AgentState(
        topic=topic,
        owner_id=owner_id,
        run_id=run_id,
        plan=None,
        existing_graph=None,
        search_hits=[],
        search_attempts=0,
        documents=[],
        source_notes=[],
        analysis=None,
        structured=None,
        critique=None,
        critique_attempts=0,
        committed_entity_ids=[],
        committed_relationship_ids=[],
        committed_entities=[],
        skipped=[],
    )
