"""``analyze_one`` (fan-out, one branch per source) + ``synthesize`` (fan-in).

``fetch`` dispatches one ``analyze_one`` per fetched document via ``Send``; each
appends a note to ``source_notes`` (an ``operator.add`` reducer). ``synthesize``
runs once, after every branch, and folds the notes into the final ``analysis``.
Smaller context per LLM call is kinder to a small local model.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.deps import AgentDeps
from app.agent.fetch import FetchedDoc
from app.agent.graph_state import AgentState
from app.agent.nodes._common import format_digest, text_of
from app.agent.prompts import prompt


async def analyze_one_node(payload: dict[str, Any], *, deps: AgentDeps) -> dict[str, Any]:
    """One source -> one note. Receives a ``Send`` payload, not the full state."""
    doc: FetchedDoc = payload["document"]
    response = await deps.chat_model.ainvoke(
        [
            SystemMessage(content=prompt("analyze_system")),
            HumanMessage(content=f"Topic: {payload['topic']}\n\nSource <{doc.url}>:\n{doc.text}"),
        ]
    )
    return {"source_notes": [f"<{doc.url}> {text_of(response.content)}"]}


async def synthesize_node(state: AgentState, *, deps: AgentDeps) -> dict[str, Any]:
    notes = state["source_notes"]
    if not notes:
        return {"analysis": "(no sources were analysed)"}
    user_prompt = (
        f"Topic: {state['topic']}\n\n"
        f"Existing graph:\n{format_digest(state['existing_graph'])}\n\n"
        f"Per-source notes:\n" + "\n\n".join(notes)
    )
    response = await deps.chat_model.ainvoke(
        [SystemMessage(content=prompt("synthesize_system")), HumanMessage(content=user_prompt)]
    )
    return {"analysis": text_of(response.content)}
