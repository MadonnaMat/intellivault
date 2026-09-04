"""app.chat.service.run_callback — the bounded tool-loop + reply chat turn."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import contextmanager
from typing import Any, cast
from uuid import uuid4

import asyncpg
import httpx
import pytest

from app.agent import service as agent_service
from app.agent.schemas import AgentRun, AgentRunCreate
from app.chat import graph_search, ollama_client, service
from app.chat.ollama_client import OllamaMessage
from app.chat.schemas import AssistantRequest
from app.graph.schemas import Entity, Relationship
from tests.chat.conftest import make_settings, make_user, new_controller, now, user_message

_POOL = cast(asyncpg.Pool, None)
_CLIENT = cast(httpx.AsyncClient, None)


def _stub_ollama(
    monkeypatch: pytest.MonkeyPatch,
    *,
    decision: OllamaMessage,
    reply_deltas: list[str],
    reply_error: Exception | None = None,
) -> list[list[dict[str, Any]]]:
    """Stub both Ollama calls; returns the message lists each call was given."""
    seen: list[list[dict[str, Any]]] = []

    async def fake_chat_once(
        client: httpx.AsyncClient,
        settings: Any,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> OllamaMessage:
        seen.append(messages)
        return decision

    async def fake_chat_stream(
        client: httpx.AsyncClient, settings: Any, messages: list[dict[str, Any]]
    ) -> AsyncIterator[str]:
        seen.append(messages)
        for delta in reply_deltas:
            yield delta
        if reply_error is not None:
            raise reply_error

    monkeypatch.setattr(ollama_client, "chat_once", fake_chat_once)
    monkeypatch.setattr(ollama_client, "chat_stream", fake_chat_stream)
    return seen


def _stub_agent_launch(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    calls: dict[str, list[Any]] = {"create": [], "enqueue": []}
    run_id = uuid4()

    async def fake_create_run(pool: Any, user_id: Any, data: AgentRunCreate) -> AgentRun:
        calls["create"].append((pool, user_id, data))
        return AgentRun(
            id=run_id, topic=data.topic, status="queued", created_at=now(), updated_at=now()
        )

    async def fake_enqueue_run(run_id_: Any) -> None:
        calls["enqueue"].append(run_id_)

    monkeypatch.setattr(agent_service, "create_run", fake_create_run)
    monkeypatch.setattr(agent_service, "enqueue_run", fake_enqueue_run)
    return calls


async def test_plain_reply_appends_streamed_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_ollama(
        monkeypatch,
        decision=OllamaMessage(role="assistant", content="", tool_calls=None),
        reply_deltas=["Hello", ", ", "world!"],
    )
    calls = _stub_agent_launch(monkeypatch)

    controller = await new_controller({"messages": []})
    await service.run_callback(
        controller,
        _request([user_message("hi")]),
        make_user(),
        pool=_POOL,
        client=_CLIENT,
        settings=make_settings(),
    )

    messages = list(controller.state["messages"])
    assert len(messages) == 2
    assert messages[0] == user_message("hi")
    assert messages[1]["role"] == "assistant"
    assert messages[1]["parts"] == [{"type": "text", "text": "Hello, world!"}]
    assert calls["create"] == []
    assert calls["enqueue"] == []


async def test_tool_call_launches_the_research_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    decision = OllamaMessage(
        role="assistant",
        content="",
        tool_calls=[
            {
                "function": {
                    "name": "launch_research_agent",
                    "arguments": {"topic": "the transistor"},
                }
            }
        ],
    )
    _stub_ollama(monkeypatch, decision=decision, reply_deltas=["On it!"])
    calls = _stub_agent_launch(monkeypatch)
    user = make_user()

    controller = await new_controller({"messages": []})
    await service.run_callback(
        controller,
        _request([user_message("research the transistor")]),
        user,
        pool=_POOL,
        client=_CLIENT,
        settings=make_settings(),
    )

    assert len(calls["create"]) == 1
    pool, user_id, data = calls["create"][0]
    assert pool is _POOL
    assert user_id == user.id
    assert data == AgentRunCreate(topic="the transistor")
    assert len(calls["enqueue"]) == 1

    messages = list(controller.state["messages"])
    assistant = messages[-1]
    assert assistant["role"] == "assistant"
    parts_by_type = {part["type"]: part for part in assistant["parts"]}
    assert parts_by_type["text"]["text"] == "On it!"
    tool_call = parts_by_type["tool-call"]
    assert tool_call["toolName"] == "launch_research_agent"
    assert tool_call["done"] is True
    assert tool_call["result"]["topic"] == "the transistor"
    assert tool_call["result"]["status"] == "queued"
    assert tool_call["result"]["id"] == str(calls["enqueue"][0])


def _entity(name: str) -> Entity:
    return Entity(
        id=uuid4(),
        owner_id=uuid4(),
        visibility="private",
        name=name,
        kind="org",
        attributes={},
        created_at=now(),
        updated_at=now(),
    )


async def test_search_tool_result_feeds_into_the_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    decision = OllamaMessage(
        role="assistant",
        content="",
        tool_calls=[
            {"function": {"name": "search_knowledge_graph", "arguments": {"query": "transistor"}}}
        ],
    )

    async def fake_search(
        settings: Any, owner_id: str, query: str
    ) -> tuple[list[Entity], list[Relationship], str | None]:
        assert query == "transistor"
        return [_entity("Bell Labs")], [], None

    monkeypatch.setattr(graph_search, "search_knowledge_graph", fake_search)
    # A search that never "launches" would otherwise keep looping up to the
    # round cap — cap it at one round so this test only exercises one call.
    settings = make_settings()
    monkeypatch.setattr(settings, "chat_tool_call_max_rounds", 1)
    seen = _stub_ollama(monkeypatch, decision=decision, reply_deltas=["Found it."])

    controller = await new_controller({"messages": []})
    await service.run_callback(
        controller,
        _request([user_message("what do we know about the transistor?")]),
        make_user(),
        pool=_POOL,
        client=_CLIENT,
        settings=settings,
    )

    messages = list(controller.state["messages"])
    assistant = messages[-1]
    tool_call = next(p for p in assistant["parts"] if p["type"] == "tool-call")
    assert tool_call["toolName"] == "search_knowledge_graph"
    assert tool_call["result"]["entities"][0]["name"] == "Bell Labs"
    assert next(p for p in assistant["parts"] if p["type"] == "text")["text"] == "Found it."

    # The reply-phase call (the last thing chat_once/chat_stream saw) carries
    # the search result as a tool turn.
    reply_history = seen[-1]
    assert any(m["role"] == "tool" and "Bell Labs" in m["content"] for m in reply_history)


async def test_search_tool_short_query_is_not_run(monkeypatch: pytest.MonkeyPatch) -> None:
    decision = OllamaMessage(
        role="assistant",
        content="",
        tool_calls=[{"function": {"name": "search_knowledge_graph", "arguments": {"query": "x"}}}],
    )
    called = False

    async def fake_search(
        *args: Any, **kwargs: Any
    ) -> tuple[list[Entity], list[Relationship], str | None]:
        nonlocal called
        called = True
        return [], [], None

    monkeypatch.setattr(graph_search, "search_knowledge_graph", fake_search)
    _stub_ollama(monkeypatch, decision=decision, reply_deltas=["Can you say more?"])

    controller = await new_controller({"messages": []})
    await service.run_callback(
        controller,
        _request([user_message("x")]),
        make_user(),
        pool=_POOL,
        client=_CLIENT,
        settings=make_settings(),
    )

    assert called is False
    messages = list(controller.state["messages"])
    assert messages[-1]["parts"] == [{"type": "text", "text": "Can you say more?"}]


async def test_search_tool_failure_is_non_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    decision = OllamaMessage(
        role="assistant",
        content="",
        tool_calls=[
            {"function": {"name": "search_knowledge_graph", "arguments": {"query": "transistor"}}}
        ],
    )

    async def failing_search(
        *args: Any, **kwargs: Any
    ) -> tuple[list[Entity], list[Relationship], str | None]:
        raise RuntimeError("neo4j down")

    monkeypatch.setattr(graph_search, "search_knowledge_graph", failing_search)
    settings = make_settings()
    monkeypatch.setattr(settings, "chat_tool_call_max_rounds", 1)
    seen = _stub_ollama(monkeypatch, decision=decision, reply_deltas=["Let me answer directly."])

    controller = await new_controller({"messages": []})
    await service.run_callback(
        controller,
        _request([user_message("transistor?")]),
        make_user(),
        pool=_POOL,
        client=_CLIENT,
        settings=settings,
    )

    messages = list(controller.state["messages"])
    assert messages[-1]["parts"] == [{"type": "text", "text": "Let me answer directly."}]
    reply_history = seen[-1]
    assert any(m["role"] == "tool" and "neo4j down" in m["content"] for m in reply_history)


async def test_tool_loop_stops_at_the_round_cap_without_a_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision = OllamaMessage(
        role="assistant",
        content="",
        tool_calls=[
            {"function": {"name": "search_knowledge_graph", "arguments": {"query": "transistor"}}}
        ],
    )

    async def fake_search(
        *args: Any, **kwargs: Any
    ) -> tuple[list[Entity], list[Relationship], str | None]:
        return [_entity("Bell Labs")], [], None

    monkeypatch.setattr(graph_search, "search_knowledge_graph", fake_search)
    settings = make_settings()
    seen = _stub_ollama(monkeypatch, decision=decision, reply_deltas=["ok"])

    controller = await new_controller({"messages": []})
    await service.run_callback(
        controller,
        _request([user_message("transistor?")]),
        make_user(),
        pool=_POOL,
        client=_CLIENT,
        settings=settings,
    )

    # settings.chat_tool_call_max_rounds decide-calls, plus the final reply call.
    assert len(seen) == settings.chat_tool_call_max_rounds + 1
    messages = list(controller.state["messages"])
    tool_call_parts = [p for p in messages[-1]["parts"] if p["type"] == "tool-call"]
    assert len(tool_call_parts) == settings.chat_tool_call_max_rounds


async def test_short_topic_is_not_launched(monkeypatch: pytest.MonkeyPatch) -> None:
    decision = OllamaMessage(
        role="assistant",
        content="",
        tool_calls=[{"function": {"name": "launch_research_agent", "arguments": {"topic": "ab"}}}],
    )
    _stub_ollama(monkeypatch, decision=decision, reply_deltas=["Can you say more?"])
    calls = _stub_agent_launch(monkeypatch)

    controller = await new_controller({"messages": []})
    await service.run_callback(
        controller,
        _request([user_message("research ab")]),
        make_user(),
        pool=_POOL,
        client=_CLIENT,
        settings=make_settings(),
    )

    assert calls["create"] == []
    messages = list(controller.state["messages"])
    assert messages[-1]["parts"] == [{"type": "text", "text": "Can you say more?"}]


async def test_decide_call_failure_adds_error_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_ollama(
        monkeypatch,
        decision=OllamaMessage(role="assistant", content=""),
        reply_deltas=[],
    )

    async def raising_chat_once(*args: Any, **kwargs: Any) -> OllamaMessage:
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(ollama_client, "chat_once", raising_chat_once)

    controller = await new_controller({"messages": []})
    await service.run_callback(
        controller,
        _request([user_message("hi")]),
        make_user(),
        pool=_POOL,
        client=_CLIENT,
        settings=make_settings(),
    )

    # Only the user's own message made it into state — no assistant turn.
    messages = list(controller.state["messages"])
    assert len(messages) == 1
    assert messages[0]["role"] == "user"


async def test_reply_call_failure_keeps_partial_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_ollama(
        monkeypatch,
        decision=OllamaMessage(role="assistant", content=""),
        reply_deltas=["partial"],
        reply_error=httpx.ReadTimeout("model stopped responding"),
    )

    controller = await new_controller({"messages": []})
    await service.run_callback(
        controller,
        _request([user_message("hi")]),
        make_user(),
        pool=_POOL,
        client=_CLIENT,
        settings=make_settings(),
    )

    messages = list(controller.state["messages"])
    assert messages[-1]["parts"] == [{"type": "text", "text": "partial"}]


class _FakeSpan:
    def __init__(self) -> None:
        self.attrs: dict[str, Any] = {}

    def set_attribute(self, key: str, value: Any) -> None:
        self.attrs[key] = value


class _FakeTracer:
    def __init__(self) -> None:
        self.opened: list[tuple[str, dict[str, Any], _FakeSpan]] = []

    @contextmanager
    def start_as_current_span(self, name: str, attributes: dict[str, Any] | None = None) -> Any:
        span = _FakeSpan()
        self.opened.append((name, attributes or {}, span))
        yield span


class _FakeProvider:
    def __init__(self) -> None:
        self.tracer = _FakeTracer()

    def get_tracer(self, _name: str) -> _FakeTracer:
        return self.tracer


async def test_chat_turn_and_tool_calls_open_spans_when_tracing_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision = OllamaMessage(
        role="assistant",
        content="",
        tool_calls=[
            {"function": {"name": "search_knowledge_graph", "arguments": {"query": "transistor"}}}
        ],
    )

    async def fake_search(
        *args: Any, **kwargs: Any
    ) -> tuple[list[Entity], list[Relationship], str | None]:
        return [_entity("Bell Labs")], [], None

    monkeypatch.setattr(graph_search, "search_knowledge_graph", fake_search)
    settings = make_settings()
    monkeypatch.setattr(settings, "chat_tool_call_max_rounds", 1)
    _stub_ollama(monkeypatch, decision=decision, reply_deltas=["Found it."])
    provider = _FakeProvider()

    controller = await new_controller({"messages": []})
    await service.run_callback(
        controller,
        _request([user_message("what do we know?")]),
        make_user(),
        pool=_POOL,
        client=_CLIENT,
        settings=settings,
        tracer_provider=provider,
    )

    names = [name for name, _attrs, _span in provider.tracer.opened]
    assert names == ["chat.turn", "chat.tool.search_knowledge_graph"]  # outer opens first

    turn_name, turn_attrs, _turn_span = provider.tracer.opened[0]
    assert turn_attrs["openinference.span.kind"] == "AGENT"

    tool_name, tool_attrs, tool_span = provider.tracer.opened[1]
    assert tool_attrs["openinference.span.kind"] == "TOOL"
    assert tool_span.attrs["chat.tool.hit_count"] == 1


async def test_no_tracer_provider_is_a_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_ollama(
        monkeypatch,
        decision=OllamaMessage(role="assistant", content="", tool_calls=None),
        reply_deltas=["hi"],
    )
    controller = await new_controller({"messages": []})
    await service.run_callback(
        controller,
        _request([user_message("hi")]),
        make_user(),
        pool=_POOL,
        client=_CLIENT,
        settings=make_settings(),
        tracer_provider=None,
    )
    messages = list(controller.state["messages"])
    assert messages[-1]["parts"] == [{"type": "text", "text": "hi"}]


def _request(messages: list[dict[str, Any]]) -> AssistantRequest:
    if not messages:
        return AssistantRequest(commands=[])
    return AssistantRequest.model_validate(
        {"commands": [{"type": "add-message", "message": messages[-1]}]}
    )
