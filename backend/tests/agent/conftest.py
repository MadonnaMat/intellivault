"""Shared fakes for the agent-loop tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import asyncpg
import httpx
import pytest
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool

from app.agent import fetch as fetch_mod
from app.agent.deps import AgentDeps, WorkerInfra
from app.agent.graph_state import initial_state
from app.config import Settings

OWNER = str(uuid4())

Row = dict[str, Any]


@pytest.fixture(autouse=True)
def stub_task_kick(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Never enqueue a real taskiq job — record run ids handed to run_agent.kiq."""
    from app.agent.tasks import run_agent

    kicked: list[str] = []

    async def _kiq(*args: Any, **_kwargs: Any) -> Any:
        kicked.append(str(args[0]))
        return SimpleNamespace(task_id="fake-task-id")

    monkeypatch.setattr(run_agent, "kiq", _kiq)
    return kicked


_TEST_SETTINGS = Settings(
    _env_file=None,
    NEO4J_PASSWORD="n",
    DATABASE_URL="postgresql://u:p@localhost:5432/db",
    OLLAMA_URL="http://ollama.test:11434",
    AGENT_MAX_SOURCES="3",
    AGENT_SOURCE_CHAR_LIMIT="2000",
)


class FakeRunnable:
    def __init__(self, payloads: list[Any]) -> None:
        self._payloads = list(payloads)

    async def ainvoke(self, _messages: Any) -> Any:
        return self._payloads.pop(0) if len(self._payloads) > 1 else self._payloads[0]


class FakeChatModel:
    """with_structured_output(schema) replays payloads keyed by schema name;
    ainvoke() returns a fixed AIMessage (the analyze node)."""

    def __init__(
        self, *, structured: dict[str, list[Any]] | None = None, text: str = "analysis notes"
    ) -> None:
        self._structured = structured or {}
        self._text = text

    def with_structured_output(self, schema: Any, **_kw: Any) -> FakeRunnable:
        return FakeRunnable(self._structured.get(schema.__name__, [{}]))

    async def ainvoke(self, _messages: Any) -> AIMessage:
        return AIMessage(content=self._text)


class FakeEmbedder:
    def __init__(
        self, *, vector: list[float] | None = None, error: Exception | None = None
    ) -> None:
        self._vector = vector if vector is not None else [0.1, 0.2, 0.3]
        self._error = error
        self.calls: list[str] = []

    async def aembed_query(self, text: str) -> list[float]:
        self.calls.append(text)
        if self._error is not None:
            raise self._error
        return self._vector


class FakeSearchTool:
    name = "search"

    def __init__(self, results: Any) -> None:
        self._results = results
        self.queries: list[str] = []

    async def ainvoke(self, args: dict[str, Any]) -> Any:
        self.queries.append(args["query"])
        return self._results


def fake_deps(
    *,
    driver: Any,
    pool: FakePool | None = None,
    chat_model: FakeChatModel | None = None,
    embedder: FakeEmbedder | None = None,
    search_tool: FakeSearchTool | None = None,
    http_client: httpx.AsyncClient | None = None,
    settings: Settings | None = None,
) -> AgentDeps:
    return AgentDeps(
        settings=settings or _TEST_SETTINGS,
        pool=cast(asyncpg.Pool, pool or FakePool()),
        driver=driver,
        http_client=http_client or cast(httpx.AsyncClient, object()),
        chat_model=cast(BaseChatModel, chat_model or FakeChatModel()),
        embedder=cast(Embeddings, embedder or FakeEmbedder(error=RuntimeError("no embedder"))),
        search_tool=cast(BaseTool, search_tool or FakeSearchTool([])),
    )


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


def fake_infra(
    *,
    driver: Any,
    pool: FakePool,
    chat_model: FakeChatModel | None = None,
    embedder: FakeEmbedder | None = None,
    search_tool: FakeSearchTool | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> WorkerInfra:
    return WorkerInfra(
        settings=_TEST_SETTINGS,
        pg_pool=cast(asyncpg.Pool, pool),
        neo4j_driver=driver,
        http_client=http_client or cast(httpx.AsyncClient, object()),
        chat_model=cast(BaseChatModel, chat_model or FakeChatModel()),
        embedder=cast(Embeddings, embedder or FakeEmbedder(error=RuntimeError("no embedder"))),
        search_tool=cast(BaseTool, search_tool or FakeSearchTool([])),
    )


def as_pool(pool: FakePool) -> asyncpg.Pool:
    """Hand a FakePool to a service function typed for asyncpg.Pool (mypy)."""
    return cast(asyncpg.Pool, pool)


# --- node-test helpers -----------------------------------------------------


@pytest.fixture
def no_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """fetch._resolve without touching real DNS: private.test -> RFC1918, else public."""

    async def _resolve(host: str, _port: int) -> list[str]:
        return ["10.0.0.1"] if host == "private.test" else ["93.184.216.34"]

    monkeypatch.setattr(fetch_mod, "_resolve", _resolve)


def make_state(**over: Any) -> Any:
    base = initial_state("history of the transistor", OWNER, str(uuid4()))
    base.update(over)  # type: ignore[typeddict-item]
    return base


def node_row(name: str, kind: str = "org") -> dict[str, Any]:
    now = datetime(2026, 9, 3, tzinfo=UTC)
    return {
        "e": {
            "id": str(uuid4()),
            "owner_id": OWNER,
            "visibility": "private",
            "name": name,
            "kind": kind,
            "attributes": "{}",
            "created_at": now,
            "updated_at": now,
        }
    }


def edge_row(kind: str = "employs") -> dict[str, Any]:
    now = datetime(2026, 9, 3, tzinfo=UTC)
    return {
        "r": {
            "id": str(uuid4()),
            "owner_id": OWNER,
            "kind": kind,
            "visibility": "private",
            "created_at": now,
            "updated_at": now,
        },
        "from_id": str(uuid4()),
        "to_id": str(uuid4()),
    }


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


__all__ = [
    "FakeChatModel",
    "FakeEmbedder",
    "FakePool",
    "FakeSearchTool",
    "OWNER",
    "Row",
    "as_pool",
    "edge_row",
    "fake_deps",
    "fake_infra",
    "find_call",
    "make_run_row",
    "make_state",
    "node_row",
    "uuid4",
]
