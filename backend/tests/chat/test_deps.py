"""app.chat.deps — FastAPI dependencies for the chat endpoint's shared clients."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from app.chat.deps import get_chat_http_client, get_tracer_provider


def _request(app: FastAPI) -> Any:
    class _Request:
        def __init__(self, app: FastAPI) -> None:
            self.app = app

    return _Request(app)


def test_get_chat_http_client_reads_app_state() -> None:
    app = FastAPI()
    sentinel = object()
    app.state.chat_http_client = sentinel
    assert get_chat_http_client(_request(app)) is sentinel


def test_get_tracer_provider_reads_app_state() -> None:
    app = FastAPI()
    assert get_tracer_provider(_request(app)) is None
    sentinel = object()
    app.state.tracer_provider = sentinel
    assert get_tracer_provider(_request(app)) is sentinel
