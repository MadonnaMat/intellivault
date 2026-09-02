"""HTTP contract for the graph routes — deps overridden, no Neo4j / Postgres."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

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
_EDGE = {
    "id": str(uuid4()),
    "owner_id": str(_USER.id),
    "kind": "employs",
    "visibility": "public",
    "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
}


@contextmanager
def graph_client(driver: FakeNeo4jDriver, *, authenticated: bool = True) -> Iterator[TestClient]:
    app = create_app()
    if authenticated:
        app.dependency_overrides[current_user] = lambda: _USER
    app.dependency_overrides[get_driver] = lambda: driver
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_get_graph_returns_visible_entities_and_edges() -> None:
    driver = FakeNeo4jDriver(
        [{"e": _NODE}], [{"r": _EDGE, "from_id": str(uuid4()), "to_id": str(uuid4())}]
    )
    with graph_client(driver) as client:
        body = client.get("/graph").json()
    assert [e["name"] for e in body["entities"]] == ["Acme"]
    assert [r["kind"] for r in body["relationships"]] == ["employs"]


def test_create_entity_returns_201() -> None:
    with graph_client(FakeNeo4jDriver([{"e": _NODE}])) as client:
        response = client.post(
            "/graph/entities", json={"name": "Acme", "kind": "org", "visibility": "public"}
        )
    assert response.status_code == 201
    assert response.json()["name"] == "Acme"


def test_create_entity_rejects_bad_visibility() -> None:
    with graph_client(FakeNeo4jDriver([{"e": _NODE}])) as client:
        response = client.post(
            "/graph/entities", json={"name": "Acme", "kind": "org", "visibility": "secret"}
        )
    assert response.status_code == 422


def test_create_relationship_returns_201() -> None:
    driver = FakeNeo4jDriver([{"r": _EDGE, "from_id": str(uuid4()), "to_id": str(uuid4())}])
    with graph_client(driver) as client:
        response = client.post(
            "/graph/relationships",
            json={"from_id": str(uuid4()), "to_id": str(uuid4()), "kind": "employs"},
        )
    assert response.status_code == 201
    assert response.json()["kind"] == "employs"


def test_create_relationship_404_when_endpoint_not_visible() -> None:
    with graph_client(FakeNeo4jDriver([], [])) as client:
        response = client.post(
            "/graph/relationships",
            json={"from_id": str(uuid4()), "to_id": str(uuid4()), "kind": "x"},
        )
    assert response.status_code == 404


def test_create_relationship_422_for_public_edge_to_private_endpoint() -> None:
    driver = FakeNeo4jDriver([], [{"from_visibility": "public", "to_visibility": "private"}])
    with graph_client(driver) as client:
        response = client.post(
            "/graph/relationships",
            json={
                "from_id": str(uuid4()),
                "to_id": str(uuid4()),
                "kind": "x",
                "visibility": "public",
            },
        )
    assert response.status_code == 422


def test_change_visibility_returns_affected_ids() -> None:
    node_id = str(uuid4())
    with graph_client(FakeNeo4jDriver([{"id": node_id, "changed": True}])) as client:
        response = client.patch(
            f"/graph/entities/{node_id}/visibility", json={"visibility": "public"}
        )
    assert response.status_code == 200
    assert response.json()["affected_ids"] == [node_id]


def test_change_visibility_noop_returns_empty() -> None:
    with graph_client(FakeNeo4jDriver([{"id": str(uuid4()), "changed": False}])) as client:
        response = client.patch(
            f"/graph/entities/{uuid4()}/visibility", json={"visibility": "public"}
        )
    assert response.status_code == 200
    assert response.json()["affected_ids"] == []


def test_change_visibility_404() -> None:
    with graph_client(FakeNeo4jDriver([])) as client:
        response = client.patch(
            f"/graph/entities/{uuid4()}/visibility", json={"visibility": "private"}
        )
    assert response.status_code == 404


def test_delete_entity_204_then_404() -> None:
    with graph_client(FakeNeo4jDriver([{"id": "e1"}])) as client:
        assert client.delete(f"/graph/entities/{uuid4()}").status_code == 204
    with graph_client(FakeNeo4jDriver([])) as client:
        assert client.delete(f"/graph/entities/{uuid4()}").status_code == 404


def test_delete_relationship_204_then_404() -> None:
    with graph_client(FakeNeo4jDriver([{"id": "r1"}])) as client:
        assert client.delete(f"/graph/relationships/{uuid4()}").status_code == 204
    with graph_client(FakeNeo4jDriver([])) as client:
        assert client.delete(f"/graph/relationships/{uuid4()}").status_code == 404


def test_graph_requires_authentication() -> None:
    with graph_client(FakeNeo4jDriver(), authenticated=False) as client:
        assert client.get("/graph").status_code == 401
