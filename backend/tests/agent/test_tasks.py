"""app.agent.tasks._run_agent — the agent_runs write path around a graph run."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

import pytest

from app.agent.llm import StructuredOutputError
from app.agent.tasks import _commit_agent_run, _guarded, _run_agent, _search_knowledge_graph
from app.config import Settings
from tests.agent.conftest import (
    FakeChatModel,
    FakeEmbedder,
    FakePool,
    FakeSearchTool,
    as_pool,
    edge_row,
    fake_infra,
    find_call,
    node_row,
)
from tests.graph.conftest import FakeNeo4jDriver

_REVIEW_SETTINGS = Settings(
    _env_file=None,
    NEO4J_PASSWORD="n",
    DATABASE_URL="postgresql://u:p@localhost:5432/db",
    OLLAMA_URL="http://ollama.test:11434",
    AGENT_REVIEW_REQUIRED="true",
)

_RUN = uuid4()
_OWNER = uuid4()


def _meta_row() -> dict[str, Any]:
    return {"id": _RUN, "user_id": _OWNER, "topic": "the transistor", "status": "queued"}


def _empty_run_chat() -> FakeChatModel:
    return FakeChatModel(
        structured={
            "Plan": [{"summary": "s", "queries": ["q"]}],
            "StructuredResult": [{"entities": [], "relationships": []}],
            "Critique": [{"verdict": "ok"}],
        },
        text="analysis",
    )


async def test_run_agent_walks_queued_running_succeeded() -> None:
    pool = FakePool(fetchrow=_meta_row())
    infra = fake_infra(
        driver=FakeNeo4jDriver([], []),  # survey list_graph reads
        pool=pool,
        chat_model=_empty_run_chat(),
        search_tool=FakeSearchTool([]),
    )
    await _run_agent(str(_RUN), infra)

    assert find_call(pool, "status = 'running'")[1] == (_RUN,)
    node_calls = [args[1] for q, args in pool.calls if "current_node = $2" in q]
    # no search hits -> no fetch/analyze_one; the synthesize/critique/lookup/enrich
    # stages still run.
    assert node_calls[:3] == ["plan", "survey_graph", "search"]
    assert node_calls[-1] == "enrich"
    assert "synthesize" in node_calls and "commit" in node_calls
    _q, ok_args = find_call(pool, "status = 'succeeded'")
    assert json.loads(ok_args[1])["analysis"] == "(no sources were analysed)"


async def test_run_agent_persists_the_plan_once() -> None:
    pool = FakePool(fetchrow=_meta_row())
    infra = fake_infra(
        driver=FakeNeo4jDriver([], []),
        pool=pool,
        chat_model=_empty_run_chat(),
        search_tool=FakeSearchTool([]),
    )
    await _run_agent(str(_RUN), infra)

    plan_writes = [
        args for q, args in pool.calls if "current_node = $2" in q and args[2] is not None
    ]
    assert len(plan_writes) == 1
    assert plan_writes[0][1] == "plan"
    assert json.loads(plan_writes[0][2]) == {"summary": "s", "queries": ["q"]}


async def test_run_agent_parks_drafts_for_review_instead_of_committing() -> None:
    pool = FakePool(fetchrow=_meta_row())
    infra = fake_infra(
        driver=FakeNeo4jDriver([], []),
        pool=pool,
        chat_model=_empty_run_chat(),
        search_tool=FakeSearchTool([]),
        settings=_REVIEW_SETTINGS,
    )
    await _run_agent(str(_RUN), infra)

    node_calls = [args[1] for q, args in pool.calls if "current_node = $2" in q]
    assert "commit" not in node_calls and "enrich" not in node_calls
    _q, args = find_call(pool, "status = 'awaiting_review'")
    assert args[0] == _RUN
    assert json.loads(args[1]) == {"entities": [], "relationships": []}
    # the research phase's partial result is parked too (analysis + skipped)
    assert json.loads(args[2])["analysis"] == "(no sources were analysed)"
    assert json.loads(args[3]) == []  # no sources fetched -> nothing parked to attach later


async def test_commit_agent_run_commits_the_parked_drafts_and_keeps_the_analysis() -> None:
    drafts = {
        "entities": [{"temp_id": "e1", "name": "Bell Labs", "kind": "org"}],
        "relationships": [],
    }
    partial = {
        "analysis": "the transistor story",
        "entities_created": 0,
        "relationships_created": 0,
        "skipped": ["fetch: dead-link"],
    }
    parked = {
        "pending": json.dumps(drafts),
        "result": json.dumps(partial),
        "source_urls": json.dumps(["https://example.com/transistor"]),
    }
    pool = FakePool(fetchrow=[_meta_row(), parked])
    driver = FakeNeo4jDriver([node_row("Bell Labs")], [{"id": "ok"}])
    infra = fake_infra(
        driver=driver,
        pool=pool,
        chat_model=_empty_run_chat(),
        settings=_REVIEW_SETTINGS,
    )
    await _commit_agent_run(str(_RUN), infra)

    _q, ok_args = find_call(pool, "status = 'succeeded'")
    assert ok_args[0] == _RUN
    final = json.loads(ok_args[1])
    assert final["entities_created"] == 1
    assert final["analysis"] == "the transistor story"  # restored from the parked result
    assert "fetch: dead-link" in final["skipped"]  # research-phase notes kept
    # the parked source_urls made it back onto the committed entity
    attach = [p for q, p in driver.calls if "SOURCED_FROM" in q][0]
    assert attach["urls"] == ["https://example.com/transistor"]


async def test_commit_agent_run_marks_failed_and_reraises_when_commit_blows_up() -> None:
    drafts = {
        "entities": [{"temp_id": "e1", "name": "X", "kind": "org"}],
        "relationships": [],
    }
    parked = {"pending": json.dumps(drafts), "result": None, "source_urls": json.dumps([])}
    pool = FakePool(fetchrow=[_meta_row(), parked])
    # no create_entity result rows -> commit_node's service call raises IndexError
    infra = fake_infra(driver=FakeNeo4jDriver(), pool=pool, settings=_REVIEW_SETTINGS)

    with pytest.raises(IndexError):
        await _commit_agent_run(str(_RUN), infra)

    _q, fail_args = find_call(pool, "status = 'failed'")
    assert fail_args[0] == _RUN


async def test_guarded_marks_failed_with_a_clear_message_on_the_deadline() -> None:
    pool = FakePool()
    state = _make_state_for_guard()

    async def _slow() -> None:
        await asyncio.sleep(1)

    with pytest.raises(TimeoutError):
        await _guarded(as_pool(pool), _RUN, state, _slow(), 0.01)

    _q, args = find_call(pool, "status = 'failed'")
    assert args[0] == _RUN and "0.01s deadline" in args[1]


def _make_state_for_guard() -> Any:
    from app.agent.graph_state import initial_state

    return initial_state("t", str(_OWNER), str(_RUN))


async def test_run_agent_marks_failed_and_reraises_on_a_node_error() -> None:
    pool = FakePool(fetchrow=_meta_row())
    # a Plan payload that never validates -> structured() raises inside plan_node
    infra = fake_infra(
        driver=FakeNeo4jDriver(),
        pool=pool,
        chat_model=FakeChatModel(structured={"Plan": [{"nope": 1}]}),
    )
    with pytest.raises(StructuredOutputError):
        await _run_agent(str(_RUN), infra)

    _q, fail_args = find_call(pool, "status = 'failed'")
    assert fail_args[0] == _RUN
    assert "StructuredOutputError" in fail_args[1]


async def test_search_knowledge_graph_task_returns_json_safe_results() -> None:
    driver = FakeNeo4jDriver([node_row("Bell Labs")], [edge_row()])
    infra = fake_infra(
        driver=driver, pool=FakePool(), embedder=FakeEmbedder(vector=[0.1, 0.2, 0.3])
    )

    result = await _search_knowledge_graph(str(_OWNER), "bell labs", 5, infra)

    assert result["entities"][0]["name"] == "Bell Labs"
    assert isinstance(result["entities"][0]["id"], str)  # UUID serialised, not a raw object
    assert len(result["relationships"]) == 1
    assert result["note"] is None
    json.dumps(result)  # the taskiq result backend needs this to actually serialise


async def test_search_knowledge_graph_task_surfaces_the_no_match_note() -> None:
    driver = FakeNeo4jDriver([], [node_row("Random Co")], [])
    infra = fake_infra(
        driver=driver, pool=FakePool(), embedder=FakeEmbedder(vector=[0.1, 0.2, 0.3])
    )

    result = await _search_knowledge_graph(str(_OWNER), "bell labs", 5, infra)

    assert result["entities"] == []
    assert result["note"] == "no matching entities found in the knowledge graph"
