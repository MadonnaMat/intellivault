"""Chat turn orchestration: decide (maybe launch the research agent), then reply.

Two Ollama calls per turn: a non-streaming "decide" call offering the
``launch_research_agent`` tool, then a streaming "reply" call with no tools.
Mutating ``controller.state`` (an ``assistant_stream`` state proxy) is how
progress reaches the client — see ``assistant_stream.state`` for the
diffing rules (string assignment becomes an efficient append-text op once
the prior value is non-empty).
"""

from __future__ import annotations

from typing import Any

import asyncpg
import httpx
from assistant_stream import RunController

from app.agent import service as agent_service
from app.agent.schemas import AgentRunCreate, AgentRunSummary
from app.auth.schemas import SessionUser
from app.chat import ollama_client
from app.chat.prompts import prompt
from app.chat.schemas import AssistantRequest
from app.chat.tools import LAUNCH_RESEARCH_AGENT, LAUNCH_RESEARCH_AGENT_TOOL
from app.config import Settings


def _new_user_message(data: AssistantRequest) -> dict[str, Any] | None:
    """The user message this turn adds, if any (an ``add-message`` command)."""
    for command in data.commands:
        if command.type == "add-message":
            return command.message.model_dump()
    return None


def _flatten(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """{role, parts} thread messages -> Ollama's {role, content} shape."""
    flat = []
    for message in messages:
        text = "".join(
            part.get("text") or ""
            for part in message.get("parts", [])
            if part.get("type") == "text"
        )
        flat.append({"role": message["role"], "content": text})
    return flat


async def run_callback(
    controller: RunController,
    data: AssistantRequest,
    user: SessionUser,
    pool: asyncpg.Pool,
    client: httpx.AsyncClient,
    settings: Settings,
) -> None:
    if controller.state is None:
        controller.state = {"messages": []}

    user_message = _new_user_message(data)
    if user_message is not None:
        controller.state["messages"].append(user_message)

    system = prompt("chat_system")
    history = list(controller.state["messages"])
    ollama_history = [{"role": "system", "content": system}, *_flatten(history)]

    try:
        decision = await ollama_client.chat_once(
            client, settings, ollama_history, tools=[LAUNCH_RESEARCH_AGENT_TOOL]
        )
    except httpx.HTTPError as exc:
        controller.add_error(f"Could not reach the language model: {exc}")
        return

    tool_calls = decision.tool_calls or []
    launch_call = next(
        (
            call
            for call in tool_calls
            if call.get("function", {}).get("name") == LAUNCH_RESEARCH_AGENT
        ),
        None,
    )

    assistant_message: dict[str, Any] = {
        "role": "assistant",
        "parts": [{"type": "text", "text": ""}],
    }
    tool_note: str | None = None

    if launch_call is not None:
        topic = str(launch_call.get("function", {}).get("arguments", {}).get("topic", "")).strip()
        if len(topic) >= 3:
            run = await agent_service.create_run(pool, user.id, AgentRunCreate(topic=topic))
            await agent_service.enqueue_run(run.id)
            summary = AgentRunSummary.model_validate(run.model_dump()).model_dump(mode="json")
            assistant_message["parts"].append(
                {
                    "type": "tool-call",
                    "toolCallId": f"launch-{run.id}",
                    "toolName": LAUNCH_RESEARCH_AGENT,
                    "argsText": f'{{"topic": "{topic}"}}',
                    "done": True,
                    "result": summary,
                }
            )
            tool_note = f"launch_research_agent(topic={topic!r}) -> queued as run {run.id}."
        else:
            tool_note = (
                "launch_research_agent was requested without a usable topic; it was not run."
            )

    controller.state["messages"].append(assistant_message)

    reply_history = [{"role": "system", "content": system}, *_flatten(controller.state["messages"])]
    if tool_note is not None:
        reply_history.append({"role": "tool", "content": tool_note})

    try:
        text = ""
        async for delta in ollama_client.chat_stream(client, settings, reply_history):
            text += delta
            controller.state["messages"][-1]["parts"][0]["text"] = text
    except httpx.HTTPError as exc:
        controller.add_error(f"Could not reach the language model: {exc}")
