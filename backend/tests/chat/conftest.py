"""Shared fakes for the chat-endpoint tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from assistant_stream import RunController

from app.auth.schemas import SessionUser
from app.config import Settings

OWNER = uuid4()

_TEST_SETTINGS = Settings(
    _env_file=None,
    NEO4J_PASSWORD="n",
    DATABASE_URL="postgresql://u:p@localhost:5432/db",
    OLLAMA_URL="http://ollama.test:11434",
)


def make_settings() -> Settings:
    return _TEST_SETTINGS


def make_user(user_id: UUID = OWNER) -> SessionUser:
    return SessionUser(id=user_id, email="chatter@example.com", display_name="Chatter")


async def new_controller(state: dict[str, object] | None = None) -> RunController:
    """A RunController backed by a live event loop but an undrained queue —
    state mutations apply synchronously regardless, so this is enough to
    assert on run_callback's effect without running the SSE plumbing."""
    return RunController(asyncio.Queue(), state_data=state)


def user_message(text: str) -> dict[str, object]:
    return {"role": "user", "parts": [{"type": "text", "text": text}]}


def now() -> datetime:
    return datetime.now(UTC)
