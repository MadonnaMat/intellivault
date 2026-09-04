"""Integration: a real agent run against a real Neo4j.

Runs the actual ``_run_agent`` + LangGraph + ``app.graph.service`` against the
disposable ``neo4j-test`` instance, with Ollama mocked over httpx (``respx``)
and a hand-rolled search tool. Proves the thing only a real engine can: the
entities the agent commits land **private**, owned by the caller, and are
invisible to another tenant — and the ``agent_runs`` row ends ``succeeded``.

Self-skips when ``neo4j-test`` is unreachable (mirrors ``tests/graph``).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
import respx
from langchain_core.tools import BaseTool
from neo4j import AsyncDriver, AsyncGraphDatabase

from app.agent import fetch
from app.agent.deps import WorkerInfra
from app.agent.llm import build_chat_model
from app.agent.tasks import _run_agent
from app.config import Settings
from app.graph import service as graph_service
from app.graph.migrations import apply_graph_migrations
from tests.agent.conftest import FakePool
from tests.graph.conftest import (
    TEST_NEO4J_PASSWORD,
    TEST_NEO4J_URI,
    TEST_NEO4J_USER,
    requires_neo4j,
)

pytestmark = requires_neo4j

_OLLAMA = "http://ollama.integration.test:11434"
_ALICE = uuid4()
_BOB = str(uuid4())

_SETTINGS = Settings(
    _env_file=None,
    NEO4J_PASSWORD="unused-here",
    DATABASE_URL="postgresql://u:p@localhost:5432/db",
    OLLAMA_URL=_OLLAMA,
    OLLAMA_CHAT_MODEL="qwen3:8b",
    OLLAMA_EMBED_MODEL="nomic-embed-text",
)


@pytest_asyncio.fixture
async def neo4j() -> AsyncIterator[AsyncDriver]:
    driver = AsyncGraphDatabase.driver(TEST_NEO4J_URI, auth=(TEST_NEO4J_USER, TEST_NEO4J_PASSWORD))
    async with driver.session(database="neo4j") as session:
        await session.run("MATCH (n) DETACH DELETE n")
    await apply_graph_migrations(driver)
    try:
        yield driver
    finally:
        await driver.close()


class _SearchTool:
    name = "search"

    async def ainvoke(self, args: dict[str, Any], *_a: Any, **_k: Any) -> Any:
        assert args["query"]
        return [{"url": "https://sources.test/transistor", "title": "Transistor history"}]


class _Embedder:
    async def aembed_query(self, _text: str) -> list[float]:
        return [0.05] * 768


class _WikiTool:
    def __init__(self, name: str) -> None:
        self.name = name

    async def ainvoke(self, _args: Any) -> Any:
        if self.name == "get_summary":
            return "A canonical description."
        if self.name == "get_related_topics":
            return {"related": ["Walter Brattain"]}
        return {"results": [{"title": "Bell Labs"}]}


def _chat_response(request: httpx.Request) -> httpx.Response:
    # The Plan / StructuredResult schema rides in the request body (as `format`
    # or a tool def, depending on the langchain-ollama version) — key off it.
    blob = request.content.decode()
    if '"queries"' in blob:
        content = json.dumps({"summary": "look into it", "queries": ["bell labs transistor 1947"]})
    elif '"entities"' in blob:
        content = json.dumps(
            {
                "entities": [
                    {"temp_id": "e1", "name": "Bell Labs", "kind": "organization"},
                    {"temp_id": "e2", "name": "William Shockley", "kind": "person"},
                ],
                "relationships": [{"from_ref": "e2", "to_ref": "e1", "kind": "worked_at"}],
            }
        )
    else:
        content = "Bell Labs, William Shockley, Bardeen and Brattain — the transistor, 1947."
    return httpx.Response(
        200,
        json={
            "model": "qwen3:8b",
            "created_at": "2026-01-01T00:00:00.000Z",
            "message": {"role": "assistant", "content": content},
            "done": True,
            "done_reason": "stop",
        },
    )


@pytest.fixture(autouse=True)
def _fake_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _resolve(_host: str, _port: int) -> list[str]:
        return ["93.184.216.34"]

    monkeypatch.setattr(fetch, "_resolve", _resolve)


def _infra(neo4j: AsyncDriver, pool: FakePool) -> WorkerInfra:
    return WorkerInfra(
        settings=_SETTINGS,
        pg_pool=cast(Any, pool),
        neo4j_driver=neo4j,
        http_client=fetch.build_http_client(_SETTINGS),
        chat_model=build_chat_model(_SETTINGS),
        embedder=cast(Any, _Embedder()),
        search_tool=cast(BaseTool, _SearchTool()),
        wikipedia_tools={
            name: cast(BaseTool, _WikiTool(name))
            for name in ("search_wikipedia", "get_summary", "get_related_topics")
        },
    )


@respx.mock
async def test_agent_run_commits_private_entities_invisible_to_others(neo4j: AsyncDriver) -> None:
    respx.post(f"{_OLLAMA}/api/chat").mock(side_effect=_chat_response)
    respx.get("https://sources.test/transistor").mock(
        return_value=httpx.Response(
            200, html="<p>The transistor was invented at Bell Labs in 1947.</p>"
        )
    )

    run_id = uuid4()
    pool = FakePool(
        fetchrow={
            "id": run_id,
            "user_id": _ALICE,
            "topic": "The invention of the transistor at Bell Labs",
            "status": "queued",
        }
    )

    await _run_agent(str(run_id), _infra(neo4j, pool))

    alice_view = {e.name for e in (await graph_service.list_graph(neo4j, str(_ALICE))).entities}
    bob_view = {e.name for e in (await graph_service.list_graph(neo4j, _BOB)).entities}

    assert {"Bell Labs", "William Shockley"} <= alice_view
    assert alice_view.isdisjoint(bob_view)  # everything the run created is private

    edges = (await graph_service.list_graph(neo4j, str(_ALICE))).relationships
    assert [r.kind for r in edges] == ["worked_at"]

    # the row was driven to success
    statuses = [q for q, _ in pool.calls]
    assert any("status = 'running'" in q for q in statuses)
    ok = next(a for q, a in pool.calls if "status = 'succeeded'" in q)
    result = json.loads(ok[1])
    assert result["entities_created"] == 2 and result["relationships_created"] == 1
