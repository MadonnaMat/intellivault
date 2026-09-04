"""FastAPI dependencies for the chat endpoint's shared clients."""

from __future__ import annotations

import httpx
from fastapi import Request

from app import observability


def get_chat_http_client(request: Request) -> httpx.AsyncClient:
    """Return the shared HTTP client used for live Ollama chat calls."""
    client: httpx.AsyncClient = request.app.state.chat_http_client
    return client


def get_tracer_provider(request: Request) -> observability.TracerProvider | None:
    """The gateway's Phoenix tracer provider, or None (tracing disabled/down)."""
    return observability.get_provider(request.app)
