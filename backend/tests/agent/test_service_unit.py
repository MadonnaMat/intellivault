"""Unit tests for app.agent.service — row mapping, 404s, mutator SQL/params."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.agent import service
from app.agent.schemas import AgentRunCreate, AgentRunResult, Plan
from tests.agent.conftest import FakePool, as_pool, find_call, make_run_row


async def test_create_run_inserts_and_maps() -> None:
    user_id = uuid4()
    pool = FakePool(fetchrow=make_run_row(user_id=user_id, topic="quantum dots"))

    run = await service.create_run(as_pool(pool), user_id, AgentRunCreate(topic="quantum dots"))

    assert run.topic == "quantum dots"
    assert run.status == "queued"
    query, args = pool.calls[0]
    assert "INSERT INTO agent_runs" in query
    assert args == (user_id, "quantum dots")


async def test_run_parses_jsonb_plan_and_result() -> None:
    row = make_run_row(
        status="succeeded",
        plan=json.dumps({"summary": "s", "queries": ["a", "b"]}),
        result=json.dumps(
            {"analysis": "done", "entities_created": 2, "relationships_created": 1, "skipped": []}
        ),
        committed_entity_ids=[uuid4(), uuid4()],
    )
    run = await service.get_run(as_pool(FakePool(fetchrow=row)), uuid4(), uuid4())

    assert run.plan == Plan(summary="s", queries=["a", "b"])
    assert run.result == AgentRunResult(
        analysis="done", entities_created=2, relationships_created=1
    )
    assert len(run.committed_entity_ids) == 2


async def test_run_accepts_already_decoded_jsonb() -> None:
    # If a codec ever decodes JSONB to dict, _load must still cope.
    row = make_run_row(plan={"summary": "s", "queries": ["q"]})
    run = await service.get_run(as_pool(FakePool(fetchrow=row)), uuid4(), uuid4())
    assert run.plan is not None and run.plan.queries == ["q"]


async def test_get_run_404_when_missing_or_foreign() -> None:
    with pytest.raises(HTTPException) as exc:
        await service.get_run(as_pool(FakePool(fetchrow=None)), uuid4(), uuid4())
    assert exc.value.status_code == 404


async def test_list_runs_maps_summaries_and_scopes_by_user() -> None:
    user_id = uuid4()
    pool = FakePool(fetch=[make_run_row(topic="a"), make_run_row(topic="b")])
    runs = await service.list_runs(as_pool(pool), user_id)

    assert [r.topic for r in runs] == ["a", "b"]
    query, args = pool.calls[0]
    assert "ORDER BY created_at DESC" in query
    assert args == (user_id,)


async def test_get_run_internal_exposes_owner_id_as_str() -> None:
    user_id, run_id = uuid4(), uuid4()
    pool = FakePool(fetchrow={"id": run_id, "user_id": user_id, "topic": "t", "status": "queued"})
    meta = await service.get_run_internal(as_pool(pool), run_id)

    assert meta.owner_id == str(user_id)
    assert meta.topic == "t"
    assert pool.calls[0][1] == (run_id,)


async def test_get_run_internal_raises_lookup_error_when_absent() -> None:
    with pytest.raises(LookupError):
        await service.get_run_internal(as_pool(FakePool(fetchrow=None)), uuid4())


async def test_record_node_sends_plan_json_only_when_given() -> None:
    run_id = uuid4()
    pool = FakePool()
    await service.record_node(as_pool(pool), run_id, "plan", plan=Plan(summary="s", queries=["q"]))
    await service.record_node(as_pool(pool), run_id, "search")

    _, with_plan = pool.calls[0]
    _, without_plan = pool.calls[1]
    assert with_plan[0] == run_id and with_plan[1] == "plan"
    assert json.loads(with_plan[2]) == {"summary": "s", "queries": ["q"]}
    assert without_plan[2] is None


async def test_mark_running_and_appends_target_the_row() -> None:
    run_id, entity_id, rel_id = uuid4(), uuid4(), uuid4()
    pool = FakePool()
    await service.mark_running(as_pool(pool), run_id)
    await service.append_committed_entity(as_pool(pool), run_id, entity_id)
    await service.append_committed_relationship(as_pool(pool), run_id, rel_id)

    assert find_call(pool, "status = 'running'")[1] == (run_id,)
    assert find_call(pool, "array_append(committed_entity_ids")[1] == (run_id, entity_id)
    assert find_call(pool, "array_append(committed_relationship_ids")[1] == (run_id, rel_id)


async def test_mark_succeeded_and_failed_write_final_state() -> None:
    run_id = uuid4()
    ents, rels = [uuid4()], [uuid4()]
    pool = FakePool()
    result = AgentRunResult(analysis="a", entities_created=1, relationships_created=1)

    await service.mark_succeeded(as_pool(pool), run_id, result, ents, rels)
    await service.mark_failed(as_pool(pool), run_id, "boom", ents, rels)

    _, ok_args = find_call(pool, "status = 'succeeded'")
    assert ok_args[0] == run_id
    assert json.loads(ok_args[1])["analysis"] == "a"
    assert ok_args[2] == ents and ok_args[3] == rels

    _, fail_args = find_call(pool, "status = 'failed'")
    assert fail_args[:2] == (run_id, "boom")


async def test_enqueue_run_is_a_noop_for_now() -> None:
    # Wired to the broker in a later slice; today it must simply not raise.
    await service.enqueue_run(uuid4())
