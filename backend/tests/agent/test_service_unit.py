"""Unit tests for app.agent.service — row mapping, 404s, mutator SQL/params."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.agent import service
from app.agent.schemas import (
    AgentRunCreate,
    AgentRunResult,
    AgentRunReview,
    DraftEntity,
    Plan,
    StructuredResult,
)
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


async def test_enqueue_run_kicks_the_task(stub_task_kick: list[str]) -> None:
    run_id = uuid4()
    await service.enqueue_run(run_id)
    assert stub_task_kick == [str(run_id)]


async def test_submit_review_approve_stores_edited_drafts() -> None:
    user_id, run_id = uuid4(), uuid4()
    row = make_run_row(
        id=run_id, status="awaiting_review", pending={"entities": [], "relationships": []}
    )
    pool = FakePool(fetchrow=[row, make_run_row(id=run_id, status="running")])
    review = AgentRunReview.model_validate(
        {"decision": "approve", "entities": [{"temp_id": "e1", "name": "X", "kind": "org"}]}
    )
    run = await service.submit_review(as_pool(pool), user_id, run_id, review)

    assert run.status == "running"
    _q, args = find_call(pool, "status = 'running'")
    assert json.loads(args[1])["entities"][0]["name"] == "X"


async def test_submit_review_reject_cancels() -> None:
    run_id = uuid4()
    pool = FakePool(
        fetchrow=[
            make_run_row(id=run_id, status="awaiting_review"),
            make_run_row(id=run_id, status="cancelled"),
        ]
    )
    run = await service.submit_review(
        as_pool(pool), uuid4(), run_id, AgentRunReview(decision="reject")
    )
    assert run.status == "cancelled"


async def test_submit_review_409_when_not_awaiting() -> None:
    pool = FakePool(fetchrow=make_run_row(status="succeeded"))
    with pytest.raises(HTTPException) as exc:
        await service.submit_review(
            as_pool(pool), uuid4(), uuid4(), AgentRunReview(decision="approve")
        )
    assert exc.value.status_code == 409


async def test_submit_review_404_when_missing() -> None:
    with pytest.raises(HTTPException) as exc:
        await service.submit_review(
            as_pool(FakePool(fetchrow=None)), uuid4(), uuid4(), AgentRunReview(decision="approve")
        )
    assert exc.value.status_code == 404


async def test_mark_awaiting_review_parks_drafts_result_and_source_urls() -> None:
    run_id = uuid4()
    pool = FakePool()
    drafts = StructuredResult(entities=[DraftEntity(temp_id="e1", name="P", kind="n")])
    result = AgentRunResult(analysis="a", entities_created=0, relationships_created=0)

    await service.mark_awaiting_review(
        as_pool(pool), run_id, drafts, result, ["https://example.com/x"]
    )

    _q, args = find_call(pool, "status = 'awaiting_review'")
    assert args[0] == run_id
    assert json.loads(args[1])["entities"][0]["name"] == "P"
    assert json.loads(args[2])["analysis"] == "a"
    assert json.loads(args[3]) == ["https://example.com/x"]


async def test_load_parked_parses_drafts_and_partial_result() -> None:
    row = make_run_row(
        pending=json.dumps({"entities": [{"temp_id": "e1", "name": "P", "kind": "n"}]}),
        result=json.dumps(
            {
                "analysis": "found things",
                "entities_created": 0,
                "relationships_created": 0,
                "skipped": ["fetch: x"],
            }
        ),
        source_urls=json.dumps(["https://example.com/x"]),
    )
    parked = await service.load_parked(as_pool(FakePool(fetchrow=row)), uuid4())
    assert parked.drafts.entities[0].name == "P"
    assert parked.partial is not None
    assert parked.partial.analysis == "found things"
    assert parked.partial.skipped == ["fetch: x"]
    assert parked.source_urls == ["https://example.com/x"]


async def test_load_parked_tolerates_a_missing_row() -> None:
    parked = await service.load_parked(as_pool(FakePool(fetchrow=None)), uuid4())
    assert parked.drafts.entities == [] and parked.partial is None
    assert parked.source_urls == []


async def test_stream_run_emits_one_event_per_change_then_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def instant_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.agent.service.asyncio.sleep", instant_sleep)

    t0 = datetime(2026, 9, 3, tzinfo=UTC)
    t1 = datetime(2026, 9, 3, 0, 0, 1, tzinfo=UTC)
    rows = [
        make_run_row(status="running", updated_at=t0),  # first poll: always emits
        make_run_row(status="running", updated_at=t0),  # unchanged: no event
        make_run_row(status="succeeded", updated_at=t1),  # changed + terminal: emits, then stops
    ]
    pool = FakePool(fetchrow=rows)

    chunks = [chunk async for chunk in service.stream_run(as_pool(pool), uuid4(), uuid4())]

    status_events = [c for c in chunks if c.startswith(b"event: status")]
    assert len(status_events) == 2
    assert b'"status": "running"' in status_events[0]
    assert b'"status": "succeeded"' in status_events[1]
    # Exactly 3 polls happened (one per scripted row) and then the generator
    # returned on its own — nothing left in the FakePool's queue.
    assert len(pool.calls) == 3


async def test_stream_run_stops_on_the_first_awaiting_review() -> None:
    row = make_run_row(status="awaiting_review")
    pool = FakePool(fetchrow=row)

    chunks = [chunk async for chunk in service.stream_run(as_pool(pool), uuid4(), uuid4())]

    assert len(chunks) == 1
    assert len(pool.calls) == 1


async def test_stream_run_propagates_404_for_a_missing_run() -> None:
    pool = FakePool(fetchrow=None)

    with pytest.raises(HTTPException) as exc_info:
        async for _ in service.stream_run(as_pool(pool), uuid4(), uuid4()):
            pass
    assert exc_info.value.status_code == 404
