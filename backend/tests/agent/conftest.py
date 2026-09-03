"""Shared fakes for the agent-loop tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import asyncpg

Row = dict[str, Any]


class FakePool:
    """asyncpg.Pool stand-in — records (query, args) and replays scripted rows.

    ``fetchrow`` / ``fetch`` take either a value or a zero-arg callable (so a
    test can return a different row per call).
    """

    def __init__(
        self,
        *,
        fetchrow: Row | list[Row] | Callable[[], Any] | None = None,
        fetch: list[Row] | Callable[[], Any] | None = None,
    ) -> None:
        self._fetchrow = fetchrow
        self._fetch = fetch if fetch is not None else []
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append((query, args))
        value = self._fetchrow
        if callable(value):
            return value()
        if isinstance(value, list):  # a scripted sequence, one row per call
            return value.pop(0) if value else None
        return value

    async def fetch(self, query: str, *args: Any) -> Any:
        self.calls.append((query, args))
        rows = self._fetch() if callable(self._fetch) else self._fetch
        return rows if rows is not None else []

    async def execute(self, query: str, *args: Any) -> str:
        self.calls.append((query, args))
        return "UPDATE 1"


def as_pool(pool: FakePool) -> asyncpg.Pool:
    """Hand a FakePool to a service function typed for asyncpg.Pool (mypy)."""
    return cast(asyncpg.Pool, pool)


def make_run_row(**overrides: Any) -> Row:
    """A full agent_runs row as _run() expects it."""
    now = datetime(2026, 9, 3, tzinfo=UTC)
    row: Row = {
        "id": uuid4(),
        "user_id": uuid4(),
        "topic": "history of the transistor",
        "status": "queued",
        "current_node": None,
        "plan": None,
        "result": None,
        "committed_entity_ids": [],
        "committed_relationship_ids": [],
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    row.update(overrides)
    return row


def find_call(pool: FakePool, needle: str) -> tuple[str, tuple[Any, ...]]:
    """The first recorded call whose SQL contains ``needle``."""
    for query, args in pool.calls:
        if needle in query:
            return query, args
    raise AssertionError(f"no call matching {needle!r} in {[q for q, _ in pool.calls]}")


__all__ = ["FakePool", "Row", "as_pool", "find_call", "make_run_row", "uuid4"]
