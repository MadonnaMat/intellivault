"""The app lifespan opens shared clients and closes them on shutdown."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.health.checks import HealthProbes
from app.main import create_app


@pytest.fixture
def closed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    order: list[str] = []

    class FakePgPool:
        async def close(self) -> None:
            order.append("pg")

    class FakeDriver:
        async def close(self) -> None:
            order.append("neo4j")

    class FakeHttpClient:
        async def aclose(self) -> None:
            order.append("http")

    async def fake_create_pool(*_args: Any, **_kwargs: Any) -> FakePgPool:
        return FakePgPool()

    monkeypatch.setattr("app.main.asyncpg.create_pool", fake_create_pool)
    monkeypatch.setattr("app.main.AsyncGraphDatabase.driver", lambda *a, **k: FakeDriver())
    monkeypatch.setattr("app.main.httpx.AsyncClient", lambda *a, **k: FakeHttpClient())
    return order


def test_lifespan_wires_and_tears_down(closed: list[str]) -> None:
    app = create_app()
    with TestClient(app):
        assert isinstance(app.state.health_probes, HealthProbes)
        assert app.state.pg_pool is app.state.health_probes.pg_pool
    assert closed == ["http", "neo4j", "pg"]
