"""app.agent.tasks._run_agent — the agent_runs write path around a graph run."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest

from app.agent.llm import StructuredOutputError
from app.agent.tasks import _run_agent
from tests.agent.conftest import FakeChatModel, FakePool, FakeSearchTool, fake_infra, find_call
from tests.graph.conftest import FakeNeo4jDriver

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
