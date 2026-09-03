"""``structure`` — extract entities + relationships from the analysis notes.

Deduped against the existing-graph digest (a draft that matches an existing
entity gets its ``existing_id`` set — link, don't create). Repeated unparseable
output is recorded and an empty result returned so the run still succeeds.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.deps import AgentDeps
from app.agent.graph_state import AgentState
from app.agent.llm import StructuredOutputError, structured
from app.agent.nodes._common import format_digest
from app.agent.prompts import prompt
from app.agent.schemas import GraphDigest, StructuredResult


def _dedupe_against_existing(
    result: StructuredResult, digest: GraphDigest | None
) -> StructuredResult:
    if digest is None or not digest.entities:
        return result
    by_key = {(e.name.lower(), e.kind.lower()): e.id for e in digest.entities}
    entities = [
        d.model_copy(update={"existing_id": by_key[(d.name.lower(), d.kind.lower())]})
        if d.existing_id is None and (d.name.lower(), d.kind.lower()) in by_key
        else d
        for d in result.entities
    ]
    return result.model_copy(update={"entities": entities})


async def structure_node(state: AgentState, *, deps: AgentDeps) -> dict[str, Any]:
    skipped = list(state["skipped"])
    user_prompt = (
        f"Topic: {state['topic']}\n\n"
        f"Existing graph:\n{format_digest(state['existing_graph'])}\n\n"
        f"Analysis:\n{state['analysis'] or '(none)'}"
    )
    try:
        result = await structured(
            deps.chat_model,
            StructuredResult,
            [
                SystemMessage(content=prompt("structure_system")),
                HumanMessage(content=user_prompt),
            ],
        )
    except StructuredOutputError as exc:
        skipped.append(f"structure: {exc}")
        return {"structured": StructuredResult(), "skipped": skipped}
    return {
        "structured": _dedupe_against_existing(result, state["existing_graph"]),
        "skipped": skipped,
    }
