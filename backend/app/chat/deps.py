"""FastAPI dependency for the chat endpoint's shared Ollama HTTP client."""

from __future__ import annotations

import httpx
from fastapi import Request


def get_chat_http_client(request: Request) -> httpx.AsyncClient:
    """Return the shared HTTP client used for live Ollama chat calls."""
    client: httpx.AsyncClient = request.app.state.chat_http_client
    return client
