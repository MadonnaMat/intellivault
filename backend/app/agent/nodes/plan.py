"""``plan`` — turn the topic into a summary + web-search queries."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.deps import AgentDeps
from app.agent.graph_state import AgentState
from app.agent.llm import structured
from app.agent.prompts import prompt
from app.agent.schemas import Plan


async def plan_node(state: AgentState, *, deps: AgentDeps) -> dict[str, Any]:
    plan = await structured(
        deps.chat_model,
        Plan,
        [
            SystemMessage(content=prompt("plan_system")),
            HumanMessage(content=f"Topic: {state['topic']}"),
        ],
    )
    return {"plan": plan}
