"""A dependency-free Ollama ``/api/chat`` client for the gateway process.

Deliberately not ``langchain_ollama.ChatOllama`` (used by the worker, see
``app/agent/llm.py``) — importing it here would pull ``langchain_ollama`` into
the gateway's import path, which ``tests/agent/test_imports.py`` forbids. This
talks Ollama's native REST API directly over the shared ``httpx.AsyncClient``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic import BaseModel

from app.config import Settings


class OllamaMessage(BaseModel):
    role: str
    content: str = ""
    tool_calls: list[dict[str, Any]] | None = None


def _base_payload(settings: Settings, messages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "model": settings.ollama_chat_model,
        "messages": messages,
        "think": settings.agent_llm_reasoning,
        "options": {"temperature": settings.agent_llm_temperature},
    }


async def chat_once(
    client: httpx.AsyncClient,
    settings: Settings,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
) -> OllamaMessage:
    """One non-streaming turn, optionally offering tools for the model to call."""
    payload = _base_payload(settings, messages) | {"stream": False}
    if tools:
        payload["tools"] = tools
    response = await client.post(f"{settings.ollama_url}/api/chat", json=payload)
    response.raise_for_status()
    data = response.json()
    return OllamaMessage.model_validate(data["message"])


async def embed_query(client: httpx.AsyncClient, settings: Settings, text: str) -> list[float]:
    """Embed one string via Ollama's native ``/api/embed`` endpoint — the
    ``search_knowledge_graph`` tool's vector, computed live in the gateway
    (the worker instead uses ``langchain_ollama.OllamaEmbeddings``, see
    ``app/agent/deps.py``, which this module deliberately avoids importing)."""
    payload = {"model": settings.ollama_embed_model, "input": text}
    response = await client.post(f"{settings.ollama_url}/api/embed", json=payload)
    response.raise_for_status()
    data = response.json()
    embedding: list[float] = data["embeddings"][0]
    return embedding


async def chat_stream(
    client: httpx.AsyncClient,
    settings: Settings,
    messages: list[dict[str, Any]],
) -> AsyncIterator[str]:
    """Stream content deltas for a turn with no tools offered."""
    payload = _base_payload(settings, messages) | {"stream": True}
    async with client.stream("POST", f"{settings.ollama_url}/api/chat", json=payload) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            delta = chunk.get("message", {}).get("content", "")
            if delta:
                yield delta
            if chunk.get("done"):
                break
