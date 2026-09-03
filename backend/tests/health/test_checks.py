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
MCP = "http://mcp.test:8770/mcp"
WIKI_MCP = "http://wiki-mcp.test:8771/mcp"


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


class _FakeRedis:
    """Stands in for redis.asyncio.Redis — records that aclose() ran."""

    last: _FakeRedis | None = None

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error
        self.closed = False

    async def ping(self) -> bool:
        if self._error is not None:
            raise self._error
        return True

    async def aclose(self) -> None:
        self.closed = True


def _redis_stub(error: Exception | None = None) -> type:
    """A drop-in for checks.Redis whose from_url() yields a fresh _FakeRedis."""

    def from_url(_url: str) -> _FakeRedis:
        _FakeRedis.last = _FakeRedis(error)
        return _FakeRedis.last

    return type("_RedisStub", (), {"from_url": staticmethod(from_url)})


@pytest.fixture(autouse=True)
def _stub_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default: the redis probe passes. Tests that need a failure re-patch checks.Redis."""
    monkeypatch.setattr(checks, "Redis", _redis_stub())


def _probes(client: httpx.AsyncClient, **overrides: Any) -> HealthProbes:
    settings = Settings(
        _env_file=None,
        NEO4J_PASSWORD="x",
        DATABASE_URL="postgresql://u:p@localhost:5432/db",
        OLLAMA_URL=OLLAMA,
        PHOENIX_COLLECTOR_ENDPOINT=PHOENIX,
        AGENT_SEARCH_MCP_URL=MCP,
        AGENT_WIKIPEDIA_MCP_URL=WIKI_MCP,
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


def _mock_healthy_http(*, phoenix: int = 200, ollama_models: list[str] | None = None) -> None:
    models = ollama_models if ollama_models is not None else ["nomic-embed-text", "qwen3:8b"]
    respx.get(f"{PHOENIX}/healthz").mock(return_value=httpx.Response(phoenix))
    respx.get(f"{OLLAMA}/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": m} for m in models]})
    )
    # streamable-HTTP endpoints reject a bare GET
    respx.get(MCP).mock(return_value=httpx.Response(406))
    respx.get(WIKI_MCP).mock(return_value=httpx.Response(406))


@respx.mock
@pytest.mark.asyncio
async def test_gather_all_ok() -> None:
    _mock_healthy_http(ollama_models=["nomic-embed-text:latest", "qwen3:8b"])
    async with httpx.AsyncClient() as client:
        statuses = {s.name: s for s in await gather_health(_probes(client))}

    assert all(s.ok for s in statuses.values())
    assert not any(s.degraded for s in statuses.values())


@respx.mock
@pytest.mark.asyncio
async def test_ollama_missing_model_is_degraded() -> None:
    _mock_healthy_http(ollama_models=["qwen3:8b"])
    async with httpx.AsyncClient() as client:
        statuses = {s.name: s for s in await gather_health(_probes(client))}

    assert statuses["ollama"].ok is True
    assert statuses["ollama"].degraded is True
    assert "nomic-embed-text" in statuses["ollama"].detail


@respx.mock
@pytest.mark.asyncio
async def test_phoenix_down_and_neo4j_error() -> None:
    _mock_healthy_http(phoenix=500)
    async with httpx.AsyncClient() as client:
        probes = _probes(client, neo4j_driver=_FakeNeo4jDriver(RuntimeError("boom")))
        statuses = {s.name: s for s in await gather_health(probes)}

    assert statuses["phoenix"].ok is False
    assert statuses["phoenix"].critical is False  # observability-only
    assert statuses["neo4j"].ok is False
    assert statuses["neo4j"].critical is True
    assert "boom" in statuses["neo4j"].detail
    assert statuses["postgres"].ok is True


@respx.mock
@pytest.mark.asyncio
async def test_mcp_probes_reachable_on_any_non_5xx() -> None:
    _mock_healthy_http()
    async with httpx.AsyncClient() as client:
        statuses = {s.name: s for s in await gather_health(_probes(client))}
    for name in ("search-mcp", "wikipedia-mcp"):
        assert statuses[name].ok is True
        assert statuses[name].critical is False


@respx.mock
@pytest.mark.asyncio
async def test_search_mcp_down_is_degraded_not_down() -> None:
    _mock_healthy_http()
    respx.get(MCP).mock(return_value=httpx.Response(502))
    async with httpx.AsyncClient() as client:
        statuses = {s.name: s for s in await gather_health(_probes(client))}
    assert statuses["search-mcp"].ok is False
    assert statuses["search-mcp"].critical is False


@respx.mock
@pytest.mark.asyncio
async def test_redis_reachable() -> None:
    _mock_healthy_http()
    async with httpx.AsyncClient() as client:
        statuses = {s.name: s for s in await gather_health(_probes(client))}

    assert statuses["redis"].ok is True
    assert statuses["redis"].critical is False
    assert _FakeRedis.last is not None and _FakeRedis.last.closed is True


@respx.mock
@pytest.mark.asyncio
async def test_redis_unreachable_is_degraded_not_down(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_healthy_http()
    monkeypatch.setattr(checks, "Redis", _redis_stub(ConnectionError("refused")))

    async with httpx.AsyncClient() as client:
        statuses = {s.name: s for s in await gather_health(_probes(client))}

    assert statuses["redis"].ok is False
    assert statuses["redis"].critical is False  # only enqueue degrades, never down
    assert "refused" in statuses["redis"].detail
    assert _FakeRedis.last is not None and _FakeRedis.last.closed is True  # aclose() still ran


@respx.mock
@pytest.mark.asyncio
async def test_gather_bounds_a_stuck_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """A probe that overruns the overall deadline is reported failed, not awaited."""
    monkeypatch.setattr(checks, "OVERALL_TIMEOUT_SECONDS", 0.1)
    _mock_healthy_http()

    async def stuck(_probes: object) -> tuple[str, bool]:
        await asyncio.shield(asyncio.sleep(5))
        return "never", False

    monkeypatch.setattr(checks, "_check_phoenix", stuck)

    async with httpx.AsyncClient() as client:
        statuses = {s.name: s for s in await gather_health(_probes(client))}

    assert statuses["phoenix"].ok is False
    assert "did not return" in statuses["phoenix"].detail
    assert statuses["postgres"].ok is True
    assert statuses["ollama"].ok is True
