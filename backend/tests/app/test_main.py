"""create_app wiring — the docs / Scalar surface and the docs_enabled switch."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

_BASE = {"NEO4J_PASSWORD": "x", "DATABASE_URL": "postgresql://u:p@localhost:5432/db"}


def _client(**extra: str) -> TestClient:
    settings = Settings(_env_file=None, **{**_BASE, **extra})  # type: ignore[arg-type]
    return TestClient(create_app(settings))


def test_scalar_explorer_is_served_when_docs_enabled() -> None:
    response = _client().get("/scalar")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "scalar" in response.text.lower()


def test_openapi_and_docs_are_available_by_default() -> None:
    client = _client()
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200


def test_docs_disabled_closes_every_interactive_route() -> None:
    client = _client(DOCS_ENABLED="false")
    for path in ("/scalar", "/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path
