"""Unit tests for the individual dependency probes."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
import respx

from app.config import Settings
from app.health import checks
from app.health.checks import HealthProbes, _measure, gather_health

OLLAMA = "http://ollama.test:11434"
PHOENIX = "http://phoenix.test:6006"


class _FakePgPool:
    def __init__(self, value: Any = 1) -> None:
        self._value = value

    async def fetchval(self, _query: str) -> Any:
        return self._value


class _FakeNeo4jDriver:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error

    async def verify_connectivity(self) -> None:
        if self._error is not None:
            raise self._error


def _probes(client: httpx.AsyncClient, **overrides: Any) -> HealthProbes:
    settings = Settings(
        _env_file=None,
        NEO4J_PASSWORD="x",
        DATABASE_URL="postgresql://u:p@localhost:5432/db",
        OLLAMA_URL=OLLAMA,
        PHOENIX_COLLECTOR_ENDPOINT=PHOENIX,
    )
    defaults: dict[str, Any] = {
        "settings": settings,
        "pg_pool": _FakePgPool(),
        "neo4j_driver": _FakeNeo4jDriver(),
        "http_client": client,
    }
    return HealthProbes(**{**defaults, **overrides})


@pytest.mark.asyncio
async def test_measure_reports_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checks, "CHECK_TIMEOUT_SECONDS", 0.01)

    async def slow() -> tuple[str, bool]:
        await asyncio.sleep(1)
        return "", False

    result = await _measure("slow", slow)
    assert result.ok is False
    assert "timed out" in result.detail


@respx.mock
@pytest.mark.asyncio
async def test_gather_all_ok() -> None:
    respx.get(f"{PHOENIX}/healthz").mock(return_value=httpx.Response(200))
    respx.get(f"{OLLAMA}/api/tags").mock(
        return_value=httpx.Response(
            200, json={"models": [{"name": "nomic-embed-text:latest"}, {"name": "qwen3:8b"}]}
        )
    )
    async with httpx.AsyncClient() as client:
        statuses = {s.name: s for s in await gather_health(_probes(client))}

    assert all(s.ok for s in statuses.values())
    assert not any(s.degraded for s in statuses.values())


@respx.mock
@pytest.mark.asyncio
async def test_ollama_missing_model_is_degraded() -> None:
    respx.get(f"{PHOENIX}/healthz").mock(return_value=httpx.Response(200))
    respx.get(f"{OLLAMA}/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "qwen3:8b"}]})
    )
    async with httpx.AsyncClient() as client:
        statuses = {s.name: s for s in await gather_health(_probes(client))}

    assert statuses["ollama"].ok is True
    assert statuses["ollama"].degraded is True
    assert "nomic-embed-text" in statuses["ollama"].detail


@respx.mock
@pytest.mark.asyncio
async def test_phoenix_down_and_neo4j_error() -> None:
    respx.get(f"{PHOENIX}/healthz").mock(return_value=httpx.Response(500))
    respx.get(f"{OLLAMA}/api/tags").mock(
        return_value=httpx.Response(
            200, json={"models": [{"name": "nomic-embed-text"}, {"name": "qwen3:8b"}]}
        )
    )
    async with httpx.AsyncClient() as client:
        probes = _probes(client, neo4j_driver=_FakeNeo4jDriver(RuntimeError("boom")))
        statuses = {s.name: s for s in await gather_health(probes)}

    assert statuses["phoenix"].ok is False
    assert statuses["neo4j"].ok is False
    assert "boom" in statuses["neo4j"].detail
    assert statuses["postgres"].ok is True
