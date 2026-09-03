"""HTTP contract for the agent routes — deps overridden, no Postgres."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast
from uuid import uuid4

import asyncpg
from fastapi.testclient import TestClient

from app.auth.dependencies import current_user
from app.auth.schemas import SessionUser
from app.db import get_pool
from app.main import create_app
from tests.agent.conftest import FakePool, make_run_row

_USER = SessionUser(id=uuid4(), email="ada@example.com", display_name="Ada")


@contextmanager
def agent_client(pool: FakePool, *, authenticated: bool = True) -> Iterator[TestClient]:
    app = create_app()
    if authenticated:
        app.dependency_overrides[current_user] = lambda: _USER
    app.dependency_overrides[get_pool] = lambda: cast(asyncpg.Pool, pool)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_create_run_returns_202_with_the_row() -> None:
    pool = FakePool(fetchrow=make_run_row(topic="superconductors", status="queued"))
    with agent_client(pool) as client:
        response = client.post("/agent/runs", json={"topic": "superconductors"})

    assert response.status_code == 202
    body = response.json()
    assert body["topic"] == "superconductors"
    assert body["status"] == "queued"
    assert "INSERT INTO agent_runs" in pool.calls[0][0]


def test_create_run_rejects_a_too_short_topic() -> None:
    with agent_client(FakePool()) as client:
        response = client.post("/agent/runs", json={"topic": "ab"})
    assert response.status_code == 422


def test_list_runs_returns_summaries() -> None:
    pool = FakePool(fetch=[make_run_row(topic="a"), make_run_row(topic="b")])
    with agent_client(pool) as client:
        body = client.get("/agent/runs").json()
    assert [r["topic"] for r in body] == ["a", "b"]


def test_get_run_200_then_404() -> None:
    run_id = uuid4()
    with agent_client(FakePool(fetchrow=make_run_row(id=run_id))) as client:
        assert client.get(f"/agent/runs/{run_id}").status_code == 200
    with agent_client(FakePool(fetchrow=None)) as client:
        assert client.get(f"/agent/runs/{uuid4()}").status_code == 404


def test_agent_requires_authentication() -> None:
    with agent_client(FakePool(), authenticated=False) as client:
        assert client.post("/agent/runs", json={"topic": "anything at all"}).status_code == 401
        assert client.get("/agent/runs").status_code == 401
