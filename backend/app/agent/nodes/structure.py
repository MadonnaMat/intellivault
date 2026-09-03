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
from app.agent.nodes._common import format_digest, format_documents
from app.agent.prompts import prompt
from app.agent.schemas import Critique, GraphDigest, StructuredResult


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
    revision = (
        f"\n\nA previous attempt was rejected: {state['critique']}" if state["critique"] else ""
    )
    user_prompt = (
        f"Topic: {state['topic']}\n\n"
        f"Existing graph:\n{format_digest(state['existing_graph'])}\n\n"
        f"Analysis:\n{state['analysis'] or '(none)'}{revision}"
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


def _format_drafts(result: StructuredResult) -> str:
    entities = "\n".join(f"- {e.temp_id}: {e.name} [{e.kind}]" for e in result.entities)
    edges = "\n".join(f"- {r.from_ref} -{r.kind}-> {r.to_ref}" for r in result.relationships)
    return f"Entities:\n{entities or '(none)'}\n\nRelationships:\n{edges or '(none)'}"


async def critique_node(state: AgentState, *, deps: AgentDeps) -> dict[str, Any]:
    """Check the drafts against the sources; ``revise`` bounces back to ``structure``."""
    result = state["structured"] or StructuredResult()
    if not result.entities:
        return {"critique": None, "critique_attempts": state["critique_attempts"] + 1}
    user_prompt = (
        f"Topic: {state['topic']}\n\n"
        f"Sources:\n{format_documents(state['documents'])}\n\n"
        f"Draft:\n{_format_drafts(result)}"
    )
    try:
        verdict = await structured(
            deps.chat_model,
            Critique,
            [SystemMessage(content=prompt("critique_system")), HumanMessage(content=user_prompt)],
        )
    except StructuredOutputError:
        verdict = Critique(verdict="ok")
    attempts = state["critique_attempts"] + 1
    if verdict.verdict == "revise":
        return {
            "critique": verdict.notes,
            "critique_attempts": attempts,
            "skipped": [*state["skipped"], f"critique (round {attempts}): {verdict.notes}"],
        }
    return {"critique": None, "critique_attempts": attempts}
