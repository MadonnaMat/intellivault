"""app.chat.graph_search — enqueue search_knowledge_graph_task and wait."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from taskiq import TaskiqResult, TaskiqResultTimeoutError

from app.agent import tasks as agent_tasks
from app.chat import graph_search
from tests.chat.conftest import make_settings

_OWNER = str(uuid4())


class _FakeTask:
    def __init__(self, result: TaskiqResult[Any] | None = None, *, timeout: bool = False) -> None:
        self._result = result
        self._timeout = timeout
        self.waited_timeout: float | None = None

    async def wait_result(self, timeout: float) -> TaskiqResult[Any]:
        self.waited_timeout = timeout
        if self._timeout:
            raise TaskiqResultTimeoutError(timeout=timeout)
        assert self._result is not None
        return self._result


def _ok_result(**data: Any) -> TaskiqResult[Any]:
    return TaskiqResult(is_err=False, log=None, return_value=data, execution_time=0.01)


def _err_result(error: str) -> TaskiqResult[Any]:
    return TaskiqResult(
        is_err=True, log=None, return_value=None, execution_time=0.01, error=RuntimeError(error)
    )


async def test_search_knowledge_graph_enqueues_and_maps_the_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entity_id = str(uuid4())
    owner_id = str(uuid4())
    task = _FakeTask(
        _ok_result(
            entities=[
                {
                    "id": entity_id,
                    "owner_id": owner_id,
                    "visibility": "private",
                    "name": "Bell Labs",
                    "kind": "org",
                    "attributes": {},
                    "sources": [],
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ],
            relationships=[],
            note=None,
        )
    )
    seen: dict[str, Any] = {}

    async def fake_kiq(owner_id_: str, query: str, limit: int) -> _FakeTask:
        seen["args"] = (owner_id_, query, limit)
        return task

    monkeypatch.setattr(agent_tasks.search_knowledge_graph_task, "kiq", fake_kiq)
    settings = make_settings()

    entities, relationships, note = await graph_search.search_knowledge_graph(
        settings, _OWNER, "Bell Labs"
    )

    assert seen["args"] == (_OWNER, "Bell Labs", settings.chat_search_max_entities)
    assert task.waited_timeout == settings.chat_search_timeout
    assert [e.name for e in entities] == ["Bell Labs"]
    assert relationships == []
    assert note is None


async def test_search_knowledge_graph_times_out_gracefully(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _FakeTask(timeout=True)

    async def fake_kiq(*args: Any, **kwargs: Any) -> _FakeTask:
        return task

    monkeypatch.setattr(agent_tasks.search_knowledge_graph_task, "kiq", fake_kiq)

    entities, relationships, note = await graph_search.search_knowledge_graph(
        make_settings(), _OWNER, "Bell Labs"
    )

    assert entities == []
    assert relationships == []
    assert note == "search timed out"


async def test_search_knowledge_graph_surfaces_a_worker_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _FakeTask(_err_result("neo4j down"))

    async def fake_kiq(*args: Any, **kwargs: Any) -> _FakeTask:
        return task

    monkeypatch.setattr(agent_tasks.search_knowledge_graph_task, "kiq", fake_kiq)

    entities, relationships, note = await graph_search.search_knowledge_graph(
        make_settings(), _OWNER, "Bell Labs"
    )

    assert entities == []
    assert relationships == []
    assert note == "search failed: neo4j down"


def test_format_search_result_lists_entities_and_relationships() -> None:
    from app.graph.schemas import Entity, Relationship
    from tests.chat.conftest import now

    bell_labs = Entity(
        id=uuid4(),
        owner_id=uuid4(),
        visibility="private",
        name="Bell Labs",
        kind="org",
        attributes={},
        created_at=now(),
        updated_at=now(),
    )
    shockley = Entity(
        id=uuid4(),
        owner_id=uuid4(),
        visibility="private",
        name="Shockley",
        kind="person",
        attributes={},
        created_at=now(),
        updated_at=now(),
    )
    edge = Relationship(
        id=uuid4(),
        owner_id=uuid4(),
        from_id=bell_labs.id,
        to_id=shockley.id,
        kind="employs",
        visibility="private",
        created_at=now(),
        updated_at=now(),
    )

    text = graph_search.format_search_result([bell_labs, shockley], [edge], None)

    assert "- Bell Labs (org)" in text
    assert "- Shockley (person)" in text
    assert "Bell Labs -[employs]-> Shockley" in text


def test_format_search_result_empty_uses_the_graph_notes_note() -> None:
    assert graph_search.format_search_result([], [], "no matching entities") == (
        "no matching entities"
    )


def test_format_search_result_empty_default_message() -> None:
    assert (
        graph_search.format_search_result([], [], None)
        == "No matching entities found in the knowledge graph."
    )
