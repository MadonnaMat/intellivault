"""app.chat.service.run_callback — the two-phase chat turn."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast
from uuid import uuid4

import asyncpg
import httpx
import pytest

from app.agent import service as agent_service
from app.agent.schemas import AgentRun, AgentRunCreate
from app.chat import ollama_client, service
from app.chat.ollama_client import OllamaMessage
from app.chat.schemas import AssistantRequest
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


def _request(messages: list[dict[str, Any]]) -> AssistantRequest:
    if not messages:
        return AssistantRequest(commands=[])
    return AssistantRequest.model_validate(
        {"commands": [{"type": "add-message", "message": messages[-1]}]}
    )
