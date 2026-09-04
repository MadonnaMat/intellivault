"""Chat turn orchestration: resolve tools (maybe search the graph, maybe
launch the research agent), then reply.

Each turn runs a bounded decide-loop offering both ``search_knowledge_graph``
and ``launch_research_agent``, so the model can check what's already known
before deciding whether research is actually needed — then one streaming
"reply" call with no tools. Mutating ``controller.state`` (an
``assistant_stream`` state proxy) is how progress reaches the client — see
``assistant_stream.state`` for the diffing rules (string assignment becomes an
efficient append-text op once the prior value is non-empty).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import asyncpg
import httpx
from assistant_stream import RunController
from neo4j import AsyncDriver

from app.agent import service as agent_service
from app.agent.schemas import AgentRunCreate, AgentRunSummary
from app.auth.schemas import SessionUser
from app.chat import graph_search, ollama_client
from app.chat.prompts import prompt
from app.chat.schemas import AssistantRequest
from app.chat.tools import (
    LAUNCH_RESEARCH_AGENT,
    LAUNCH_RESEARCH_AGENT_TOOL,
    SEARCH_KNOWLEDGE_GRAPH,
    SEARCH_KNOWLEDGE_GRAPH_TOOL,
)
from app.config import Settings

_TOOLS = [SEARCH_KNOWLEDGE_GRAPH_TOOL, LAUNCH_RESEARCH_AGENT_TOOL]


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


async def _run_search(
    args: dict[str, Any],
    *,
    user: SessionUser,
    driver: AsyncDriver,
    client: httpx.AsyncClient,
    settings: Settings,
) -> tuple[str, dict[str, Any] | None, bool]:
    """Returns (tool note for the model, tool-call part for the UI, launched=False)."""
    query = str(args.get("query", "")).strip()
    if len(query) < 3:
        note = "search_knowledge_graph was requested without a usable query; it was not run."
        return note, None, False
    try:
        entities, relationships = await graph_search.search_knowledge_graph(
            driver, client, settings, str(user.id), query
        )
    except Exception as exc:  # noqa: BLE001 - best-effort, never fatal to the turn
        return f"search_knowledge_graph(query={query!r}) failed: {exc}", None, False

    call_args = {"query": query}
    part = {
        "type": "tool-call",
        "toolCallId": f"search-{uuid4()}",
        "toolName": SEARCH_KNOWLEDGE_GRAPH,
        "args": call_args,
        "argsText": json.dumps(call_args),
        "done": True,
        "result": {
            "entities": [e.model_dump(mode="json") for e in entities],
            "relationships": [r.model_dump(mode="json") for r in relationships],
        },
    }
    text = graph_search.format_search_result(entities, relationships)
    return f"search_knowledge_graph(query={query!r}) ->\n{text}", part, False


async def _run_launch(
    args: dict[str, Any], *, user: SessionUser, pool: asyncpg.Pool
) -> tuple[str, dict[str, Any] | None, bool]:
    """Returns (tool note for the model, tool-call part for the UI, launched)."""
    topic = str(args.get("topic", "")).strip()
    if len(topic) < 3:
        note = "launch_research_agent was requested without a usable topic; it was not run."
        return note, None, False

    run = await agent_service.create_run(pool, user.id, AgentRunCreate(topic=topic))
    await agent_service.enqueue_run(run.id)
    summary = AgentRunSummary.model_validate(run.model_dump()).model_dump(mode="json")
    call_args = {"topic": topic}
    part = {
        "type": "tool-call",
        "toolCallId": f"launch-{run.id}",
        "toolName": LAUNCH_RESEARCH_AGENT,
        "args": call_args,
        "argsText": json.dumps(call_args),
        "done": True,
        "result": summary,
    }
    return f"launch_research_agent(topic={topic!r}) -> queued as run {run.id}.", part, True


async def _call_tool(
    call: dict[str, Any],
    *,
    user: SessionUser,
    pool: asyncpg.Pool,
    driver: AsyncDriver,
    client: httpx.AsyncClient,
    settings: Settings,
) -> tuple[str, dict[str, Any] | None, bool]:
    name = call.get("function", {}).get("name")
    args = call.get("function", {}).get("arguments") or {}
    if name == SEARCH_KNOWLEDGE_GRAPH:
        return await _run_search(args, user=user, driver=driver, client=client, settings=settings)
    if name == LAUNCH_RESEARCH_AGENT:
        return await _run_launch(args, user=user, pool=pool)
    return f"{name} is not a recognized tool.", None, False


async def _resolve_tools(
    ollama_history: list[dict[str, Any]],
    *,
    user: SessionUser,
    pool: asyncpg.Pool,
    driver: AsyncDriver,
    client: httpx.AsyncClient,
    settings: Settings,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Bounded decide-loop: offer both tools, execute whatever the model
    calls, feed each result back as its own history turn, and repeat — until
    the model stops calling tools, launches research (a natural stopping
    point for the turn), or the round cap is hit."""
    notes: list[str] = []
    parts: list[dict[str, Any]] = []
    for _round in range(settings.chat_tool_call_max_rounds):
        decision = await ollama_client.chat_once(client, settings, ollama_history, tools=_TOOLS)
        tool_calls = decision.tool_calls or []
        if not tool_calls:
            break
        launched = False
        for call in tool_calls:
            note, part, did_launch = await _call_tool(
                call, user=user, pool=pool, driver=driver, client=client, settings=settings
            )
            notes.append(note)
            if part is not None:
                parts.append(part)
            ollama_history.append({"role": "tool", "content": note})
            launched = launched or did_launch
        if launched:
            break
    return notes, parts


async def run_callback(
    controller: RunController,
    data: AssistantRequest,
    user: SessionUser,
    pool: asyncpg.Pool,
    client: httpx.AsyncClient,
    settings: Settings,
    driver: AsyncDriver,
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
        tool_notes, tool_parts = await _resolve_tools(
            ollama_history, user=user, pool=pool, driver=driver, client=client, settings=settings
        )
    except httpx.HTTPError as exc:
        controller.add_error(f"Could not reach the language model: {exc}")
        return

    assistant_message: dict[str, Any] = {
        "role": "assistant",
        "parts": [{"type": "text", "text": ""}, *tool_parts],
    }
    controller.state["messages"].append(assistant_message)

    # Built from `history` (pre-placeholder), not controller.state["messages"] —
    # a trailing *empty* assistant turn in the sent history confuses some
    # models' chat templates into emitting literal <think> tags even with
    # think=False (reproduced directly against Ollama's /api/chat).
    reply_history = [{"role": "system", "content": system}, *_flatten(history)]
    for note in tool_notes:
        reply_history.append({"role": "tool", "content": note})

    try:
        text = ""
        async for delta in ollama_client.chat_stream(client, settings, reply_history):
            text += delta
            controller.state["messages"][-1]["parts"][0]["text"] = text
    except httpx.HTTPError as exc:
        controller.add_error(f"Could not reach the language model: {exc}")
