"""HTTP contract for POST /chat — deps overridden, no real Ollama/Postgres."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

import pytest
from assistant_stream import RunController
from fastapi.testclient import TestClient

from app.auth.dependencies import current_user
from app.auth.schemas import SessionUser
from app.chat import service as chat_service
from app.chat.deps import get_chat_http_client
from app.db import get_pool
from app.main import create_app

_USER = SessionUser(id=uuid4(), email="ada@example.com", display_name="Ada")

_BODY: dict[str, Any] = {
    "commands": [
        {
            "type": "add-message",
            "message": {"role": "user", "parts": [{"type": "text", "text": "hi"}]},
        }
    ],
    "state": {"messages": []},
}


@contextmanager
def chat_client(*, authenticated: bool = True) -> Iterator[TestClient]:
    app = create_app()
    if authenticated:
        app.dependency_overrides[current_user] = lambda: _USER
    app.dependency_overrides[get_pool] = lambda: None
    app.dependency_overrides[get_chat_http_client] = lambda: None
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def _fake_run_callback(
    controller: RunController, data: Any, user: Any, pool: Any, client: Any, settings: Any
) -> None:
    if controller.state is None:
        controller.state = {"messages": []}
    controller.state["messages"].append(
        {"role": "assistant", "parts": [{"type": "text", "text": "hi there"}]}
    )


def test_chat_requires_auth() -> None:
    with chat_client(authenticated=False) as client:
        response = client.post("/chat", json=_BODY)
    assert response.status_code == 401


def test_chat_streams_assistant_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_service, "run_callback", _fake_run_callback)
    with chat_client() as client:
        response = client.post("/chat", json=_BODY)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "hi there" in response.text


def test_chat_rejects_a_malformed_command() -> None:
    with chat_client() as client:
        response = client.post("/chat", json={"commands": [{"type": "not-a-real-command"}]})
    assert response.status_code == 422
