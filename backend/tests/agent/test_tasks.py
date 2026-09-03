"""app.agent.tasks._run_agent — the agent_runs write path around a graph run."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest

from app.agent.llm import StructuredOutputError
from app.agent.tasks import _commit_agent_run, _run_agent
from app.config import Settings
from tests.agent.conftest import (
    FakeChatModel,
    FakePool,
    FakeSearchTool,
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


async def test_commit_agent_run_commits_the_parked_drafts_and_succeeds() -> None:
    pending = json.dumps(
        {
            "entities": [{"temp_id": "e1", "name": "Bell Labs", "kind": "org"}],
            "relationships": [],
        }
    )
    pool = FakePool(fetchrow=_meta_row(), fetchval=pending)
    infra = fake_infra(
        driver=FakeNeo4jDriver([node_row("Bell Labs")], [{"id": "ok"}]),
        pool=pool,
        chat_model=_empty_run_chat(),
        settings=_REVIEW_SETTINGS,
    )
    await _commit_agent_run(str(_RUN), infra)

    _q, ok_args = find_call(pool, "status = 'succeeded'")
    assert ok_args[0] == _RUN
    assert json.loads(ok_args[1])["entities_created"] == 1


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
