"""HTTP contract for the graph routes — deps overridden, no Neo4j / Postgres."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import current_user
from app.auth.schemas import SessionUser
from app.graph.db import get_driver
from app.main import create_app
from tests.graph.conftest import FakeNeo4jDriver

_USER = SessionUser(id=uuid4(), email="ada@example.com", display_name="Ada")
_NODE = {
    "id": str(uuid4()),
    "owner_id": str(_USER.id),
    "visibility": "public",
    "name": "Acme",
    "kind": "org",
    "attributes": "{}",
    "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
}


def _client(driver: FakeNeo4jDriver) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[current_user] = lambda: _USER
    app.dependency_overrides[get_driver] = lambda: driver
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def get_graph_client() -> Iterator[TestClient]:
    yield from _client(FakeNeo4jDriver([{"e": _NODE}]))


def test_get_graph_returns_visible_entities(get_graph_client: TestClient) -> None:
    response = get_graph_client.get("/graph")
    assert response.status_code == 200
    body = response.json()
    assert [e["name"] for e in body["entities"]] == ["Acme"]


def test_create_entity_returns_201(get_graph_client: TestClient) -> None:
    response = get_graph_client.post(
        "/graph/entities", json={"name": "Acme", "kind": "org", "visibility": "public"}
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Acme"


def test_create_entity_rejects_bad_visibility(get_graph_client: TestClient) -> None:
    response = get_graph_client.post(
        "/graph/entities", json={"name": "Acme", "kind": "org", "visibility": "secret"}
    )
    assert response.status_code == 422


def test_graph_requires_authentication() -> None:
    # No current_user override: the real dependency runs and rejects.
    app = create_app()
    app.dependency_overrides[get_driver] = lambda: FakeNeo4jDriver()
    with TestClient(app) as client:
        assert client.get("/graph").status_code == 401
    app.dependency_overrides.clear()
