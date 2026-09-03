"""``analyze`` — turn the fetched sources + the graph digest into factual notes."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.deps import AgentDeps
from app.agent.graph_state import AgentState
from app.agent.nodes._common import format_digest, format_documents, text_of
from app.agent.prompts import prompt


async def analyze_node(state: AgentState, *, deps: AgentDeps) -> dict[str, Any]:
    user_prompt = (
        f"Topic: {state['topic']}\n\n"
        f"Existing graph:\n{format_digest(state['existing_graph'])}\n\n"
        f"Sources:\n{format_documents(state['documents'])}"
    )
    response = await deps.chat_model.ainvoke(
        [SystemMessage(content=prompt("analyze_system")), HumanMessage(content=user_prompt)]
    )
    return {"analysis": text_of(response.content)}
