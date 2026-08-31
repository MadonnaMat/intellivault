"""Tests for the deep /health endpoint's aggregation and status codes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import ServiceStatus


def _svc(name: str, *, ok: bool = True, degraded: bool = False) -> ServiceStatus:
    return ServiceStatus(name=name, ok=ok, degraded=degraded, detail="", latency_ms=1.0)


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    app.state.health_probes = object()  # gather_health is patched, so unused
    return TestClient(app)


def _patch_gather(monkeypatch: pytest.MonkeyPatch, services: list[ServiceStatus]) -> None:
    async def fake_gather(_probes: object) -> list[ServiceStatus]:
        return services

    monkeypatch.setattr("app.health.router.gather_health", fake_gather)


def test_all_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_gather(monkeypatch, [_svc("postgres"), _svc("ollama")])
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_degraded_is_200(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_gather(monkeypatch, [_svc("postgres"), _svc("ollama", degraded=True)])
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


def test_down_is_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_gather(monkeypatch, [_svc("postgres", ok=False), _svc("ollama", degraded=True)])
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "down"
