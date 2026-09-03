"""Drive the whole compiled graph end to end with fakes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
import respx

from app.agent import fetch
from app.agent.graph import build_graph, initial_state, run_graph
from tests.agent.conftest import FakeChatModel, FakePool, FakeSearchTool, fake_deps
from tests.graph.conftest import FakeNeo4jDriver

_OWNER = str(uuid4())
_RUN = str(uuid4())


@pytest.fixture(autouse=True)
def _no_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _resolve(_host: str, _port: int) -> list[str]:
        return ["93.184.216.34"]

    monkeypatch.setattr(fetch, "_resolve", _resolve)


def _node_row(name: str) -> dict[str, Any]:
    now = datetime(2026, 9, 3, tzinfo=UTC)
    return {
        "e": {
            "id": str(uuid4()),
            "owner_id": _OWNER,
            "visibility": "private",
            "name": name,
            "kind": "org",
            "attributes": "{}",
            "created_at": now,
            "updated_at": now,
        }
    }


def _chat() -> FakeChatModel:
    return FakeChatModel(
        structured={
            "Plan": [{"summary": "s", "queries": ["q1"]}],
            "StructuredResult": [
                {
                    "entities": [{"temp_id": "e1", "name": "Bell Labs", "kind": "org"}],
                    "relationships": [],
                }
            ],
        }
    )


@respx.mock
async def test_full_run_commits_a_private_entity() -> None:
    respx.get("https://src.test/1").mock(return_value=httpx.Response(200, html="<p>facts</p>"))
    # survey_graph: list entities, list rels; commit: one create_entity
    driver = FakeNeo4jDriver([], [], [_node_row("Bell Labs")])
    pool = FakePool()

    async with httpx.AsyncClient(follow_redirects=False) as client:
        deps = fake_deps(
            driver=driver,
            pool=pool,
            chat_model=_chat(),
            search_tool=FakeSearchTool([{"url": "https://src.test/1", "title": "S"}]),
            http_client=client,
        )
        graph = build_graph(deps)
        seen: dict[str, dict[str, Any]] = {}
        async for node_name, update in run_graph(graph, initial_state("topic", _OWNER, _RUN)):
            seen[node_name] = update

    assert list(seen) == [
        "plan",
        "survey_graph",
        "search",
        "fetch",
        "analyze",
        "structure",
        "commit",
    ]
    assert len(seen["commit"]["committed_entity_ids"]) == 1
    assert any("array_append(committed_entity_ids" in q for q, _ in pool.calls)
    create = [p for q, p in driver.calls if "CREATE (e:Entity" in q][0]
    assert create["visibility"] == "private" and create["owner_id"] == _OWNER


@respx.mock
async def test_full_run_does_not_abort_on_a_rejected_relationship() -> None:
    respx.get("https://src.test/1").mock(return_value=httpx.Response(200, html="<p>x</p>"))
    chat = FakeChatModel(
        structured={
            "Plan": [{"summary": "s", "queries": ["q1"]}],
            "StructuredResult": [
                {
                    "entities": [{"temp_id": "e1", "name": "A", "kind": "org"}],
                    "relationships": [{"from_ref": "e1", "to_ref": "e1", "kind": "self"}],
                }
            ],
        }
    )
    # survey (2) + create_entity (1) + create_relationship [] + relationship_endpoints []
    driver = FakeNeo4jDriver([], [], [_node_row("A")], [], [])

    async with httpx.AsyncClient(follow_redirects=False) as client:
        deps = fake_deps(
            driver=driver,
            pool=FakePool(),
            chat_model=chat,
            search_tool=FakeSearchTool([{"url": "https://src.test/1"}]),
            http_client=client,
        )
        final: dict[str, Any] = {}
        async for node_name, update in run_graph(
            build_graph(deps), initial_state("t", _OWNER, _RUN)
        ):
            if node_name == "commit":
                final = update

    assert final["committed_entity_ids"] and not final["committed_relationship_ids"]
    assert any("e1->e1" in note for note in final["skipped"])
