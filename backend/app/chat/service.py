"""Chat turn orchestration: resolve tools (maybe search the graph, maybe
launch the research agent), then reply.

Each turn runs a bounded decide-loop offering both ``search_knowledge_graph``
and ``launch_research_agent``, so the model can check what's already known
before deciding whether research is actually needed — then one streaming
"reply" call with no tools. Mutating ``controller.state`` (an
``assistant_stream`` state proxy) is how progress reaches the client — see
``assistant_stream.state`` for the diffing rules (string assignment becomes an
efficient append-text op once the prior value is non-empty).

The whole turn is one ``chat.turn`` (AGENT-kind) Phoenix span, with each
resolved tool call as its own ``chat.tool.*`` (TOOL-kind) child span — see
``app.observability.traced``. ``search_knowledge_graph`` runs as a LangGraph
in the worker (``app.chat.graph_search`` enqueues it and waits), so its own
node-level spans nest under that tool span via the worker's tracer, not this
one; ``launch_research_agent`` only enqueues a run here, the run's own spans
start later, in the worker, under their own root.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import asyncpg
import httpx
from assistant_stream import RunController

from app import observability
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
    settings: Settings,
    tracer_provider: observability.TracerProvider | None,
) -> tuple[str, dict[str, Any] | None, bool]:
    """Returns (tool note for the model, tool-call part for the UI, launched=False)."""
    query = str(args.get("query", "")).strip()
    if len(query) < 3:
        note = "search_knowledge_graph was requested without a usable query; it was not run."
        return note, None, False

    with observability.traced(
        tracer_provider,
        "app.chat",
        "chat.tool.search_knowledge_graph",
        kind="TOOL",
        metadata={"query": query},
    ) as span:
        try:
            entities, relationships, note_from_graph = await graph_search.search_knowledge_graph(
                settings, str(user.id), query
            )
        except Exception as exc:  # noqa: BLE001 - best-effort, never fatal to the turn
            if span is not None:
                span.set_attribute("error", True)
            return f"search_knowledge_graph(query={query!r}) failed: {exc}", None, False
        if span is not None:
            span.set_attribute("chat.tool.hit_count", len(entities))

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
    text = graph_search.format_search_result(entities, relationships, note_from_graph)
    return f"search_knowledge_graph(query={query!r}) ->\n{text}", part, False


async def _run_launch(
    args: dict[str, Any],
    *,
    user: SessionUser,
    pool: asyncpg.Pool,
    tracer_provider: observability.TracerProvider | None,
) -> tuple[str, dict[str, Any] | None, bool]:
    """Returns (tool note for the model, tool-call part for the UI, launched)."""
    topic = str(args.get("topic", "")).strip()
    if len(topic) < 3:
        note = "launch_research_agent was requested without a usable topic; it was not run."
        return note, None, False

    with observability.traced(
        tracer_provider,
        "app.chat",
        "chat.tool.launch_research_agent",
        kind="TOOL",
        metadata={"topic": topic},
    ) as span:
        run = await agent_service.create_run(pool, user.id, AgentRunCreate(topic=topic))
        await agent_service.enqueue_run(run.id)
        if span is not None:
            span.set_attribute("chat.tool.run_id", str(run.id))

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
    settings: Settings,
    tracer_provider: observability.TracerProvider | None,
) -> tuple[str, dict[str, Any] | None, bool]:
    name = call.get("function", {}).get("name")
    args = call.get("function", {}).get("arguments") or {}
    if name == SEARCH_KNOWLEDGE_GRAPH:
        return await _run_search(
            args, user=user, settings=settings, tracer_provider=tracer_provider
        )
    if name == LAUNCH_RESEARCH_AGENT:
        return await _run_launch(args, user=user, pool=pool, tracer_provider=tracer_provider)
    return f"{name} is not a recognized tool.", None, False


async def _resolve_tools(
    ollama_history: list[dict[str, Any]],
    *,
    user: SessionUser,
    pool: asyncpg.Pool,
    client: httpx.AsyncClient,
    settings: Settings,
    tracer_provider: observability.TracerProvider | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Bounded decide-loop: offer both tools, execute whatever the model
    calls, and append both the model's tool_calls turn and each tool's result
    back into ``ollama_history`` — the assistant(tool_calls) -> tool(result)
    pairing Ollama's chat API expects — and repeat, until the model stops
    calling tools, launches research (a natural stopping point for the turn),
    or the round cap is hit. ``ollama_history`` is left ready for the
    reply-phase call to continue from directly."""
    parts: list[dict[str, Any]] = []
    called: list[str] = []
    for _round in range(settings.chat_tool_call_max_rounds):
        decision = await ollama_client.chat_once(client, settings, ollama_history, tools=_TOOLS)
        tool_calls = decision.tool_calls or []
        if not tool_calls:
            break
        ollama_history.append(
            {"role": "assistant", "content": decision.content, "tool_calls": tool_calls}
        )
        launched = False
        for call in tool_calls:
            name = call.get("function", {}).get("name")
            note, part, did_launch = await _call_tool(
                call, user=user, pool=pool, settings=settings, tracer_provider=tracer_provider
            )
            called.append(str(name))
            if part is not None:
                parts.append(part)
            ollama_history.append({"role": "tool", "content": note})
            launched = launched or did_launch
        if launched:
            break
    return parts, called


async def run_callback(
    controller: RunController,
    data: AssistantRequest,
    user: SessionUser,
    pool: asyncpg.Pool,
    client: httpx.AsyncClient,
    settings: Settings,
    tracer_provider: observability.TracerProvider | None = None,
) -> None:
    if controller.state is None:
        controller.state = {"messages": []}

    user_message = _new_user_message(data)
    if user_message is not None:
        controller.state["messages"].append(user_message)

    system = prompt("chat_system")
    history = list(controller.state["messages"])
    ollama_history = [{"role": "system", "content": system}, *_flatten(history)]

    with observability.traced(
        tracer_provider,
        "app.chat",
        "chat.turn",
        kind="AGENT",
        metadata={"user_id": str(user.id), "message_count": len(history)},
    ) as span:
        try:
            tool_parts, tools_called = await _resolve_tools(
                ollama_history,
                user=user,
                pool=pool,
                client=client,
                settings=settings,
                tracer_provider=tracer_provider,
            )
        except httpx.HTTPError as exc:
            if span is not None:
                span.set_attribute("error", True)
            controller.add_error(f"Could not reach the language model: {exc}")
            return

        if span is not None and tools_called:
            span.set_attribute("chat.tools_called", tools_called)

        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "parts": [{"type": "text", "text": ""}, *tool_parts],
        }
        controller.state["messages"].append(assistant_message)

        # `ollama_history` never saw controller.state["messages"]'s placeholder
        # (it was built from `history`, captured before the append above) — a
        # trailing *empty* assistant turn in the sent history confuses some
        # models' chat templates into emitting literal <think> tags even with
        # think=False (reproduced directly against Ollama's /api/chat). It's
        # also now correctly paired (assistant tool_calls -> tool result) from
        # _resolve_tools, so the reply call continues from it directly.
        try:
            text = ""
            async for delta in ollama_client.chat_stream(client, settings, ollama_history):
                text += delta
                controller.state["messages"][-1]["parts"][0]["text"] = text
        except httpx.HTTPError as exc:
            if span is not None:
                span.set_attribute("error", True)
            controller.add_error(f"Could not reach the language model: {exc}")
