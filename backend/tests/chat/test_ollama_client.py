"""app.chat.ollama_client — the native httpx client for /api/chat."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.chat.ollama_client import chat_once, chat_stream, embed_query
from tests.chat.conftest import make_settings

_OLLAMA = "http://ollama.test:11434"


@respx.mock
async def test_chat_once_parses_the_reply() -> None:
    respx.post(f"{_OLLAMA}/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "qwen3:8b",
                "message": {"role": "assistant", "content": "hello there"},
                "done": True,
            },
        )
    )

    async with httpx.AsyncClient() as client:
        message = await chat_once(client, make_settings(), [{"role": "user", "content": "hi"}])

    assert message.role == "assistant"
    assert message.content == "hello there"
    assert message.tool_calls is None


@respx.mock
async def test_chat_once_returns_tool_calls_and_sends_the_tool_schema() -> None:
    route = respx.post(f"{_OLLAMA}/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "qwen3:8b",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "launch_research_agent", "arguments": {"topic": "x"}}}
                    ],
                },
                "done": True,
            },
        )
    )
    tool = {"type": "function", "function": {"name": "launch_research_agent"}}

    async with httpx.AsyncClient() as client:
        message = await chat_once(
            client, make_settings(), [{"role": "user", "content": "research x"}], tools=[tool]
        )

    assert message.tool_calls == [
        {"function": {"name": "launch_research_agent", "arguments": {"topic": "x"}}}
    ]
    sent = json.loads(route.calls.last.request.content)
    assert sent["tools"] == [tool]
    assert sent["stream"] is False


@respx.mock
async def test_chat_once_raises_on_a_backend_error() -> None:
    respx.post(f"{_OLLAMA}/api/chat").mock(return_value=httpx.Response(500, text="boom"))

    async with httpx.AsyncClient() as client:
        with pytest.raises(httpx.HTTPStatusError):
            await chat_once(client, make_settings(), [{"role": "user", "content": "hi"}])


@respx.mock
async def test_embed_query_posts_the_configured_model_and_returns_the_vector() -> None:
    route = respx.post(f"{_OLLAMA}/api/embed").mock(
        return_value=httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})
    )

    async with httpx.AsyncClient() as client:
        vector = await embed_query(client, make_settings(), "the transistor")

    assert vector == [0.1, 0.2, 0.3]
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"model": "nomic-embed-text", "input": "the transistor"}


@respx.mock
async def test_embed_query_raises_on_a_backend_error() -> None:
    respx.post(f"{_OLLAMA}/api/embed").mock(return_value=httpx.Response(500, text="boom"))

    async with httpx.AsyncClient() as client:
        with pytest.raises(httpx.HTTPStatusError):
            await embed_query(client, make_settings(), "the transistor")


@respx.mock
async def test_chat_stream_yields_content_deltas_and_stops_at_done() -> None:
    lines = [
        json.dumps({"message": {"content": "Hel"}, "done": False}),
        json.dumps({"message": {"content": "lo"}, "done": False}),
        json.dumps({"message": {"content": ""}, "done": True, "done_reason": "stop"}),
    ]
    respx.post(f"{_OLLAMA}/api/chat").mock(
        return_value=httpx.Response(200, content="\n".join(lines) + "\n")
    )

    async with httpx.AsyncClient() as client:
        deltas = [
            delta
            async for delta in chat_stream(
                client, make_settings(), [{"role": "user", "content": "hi"}]
            )
        ]

    assert deltas == ["Hel", "lo"]
