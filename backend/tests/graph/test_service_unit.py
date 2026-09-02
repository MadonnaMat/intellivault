"""Unit tests for app.graph.service — record→model mapping, no Neo4j."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from neo4j import AsyncDriver

from app.graph import service
from app.graph.schemas import EntityInput
from app.graph.service import _dt, _entity
from tests.graph.conftest import FakeNeo4jDriver

_OWNER = str(uuid4())
_NODE = {
    "id": str(uuid4()),
    "owner_id": _OWNER,
    "visibility": "private",
    "name": "Acme",
    "kind": "org",
    "attributes": '{"industry": "widgets"}',
    "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    "updated_at": datetime(2026, 1, 2, tzinfo=UTC),
}


class _NeoDateTime:
    def __init__(self, value: datetime) -> None:
        self._value = value

    def to_native(self) -> datetime:
        return self._value


def test_dt_passes_native_datetime_through() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert _dt(now) is now


def test_dt_converts_neo4j_datetime() -> None:
    now = datetime(2026, 3, 4, tzinfo=UTC)
    assert _dt(_NeoDateTime(now)) is now


def test_entity_parses_attributes_json() -> None:
    entity = _entity(_NODE)
    assert entity.name == "Acme"
    assert entity.attributes == {"industry": "widgets"}
    assert entity.created_at == _NODE["created_at"]


def test_entity_tolerates_empty_attributes() -> None:
    assert _entity({**_NODE, "attributes": ""}).attributes == {}
    assert _entity({k: v for k, v in _NODE.items() if k != "attributes"}).attributes == {}


async def test_create_entity_serialises_input_and_maps_result() -> None:
    driver = FakeNeo4jDriver([{"e": _NODE}])

    result = await service.create_entity(
        cast(AsyncDriver, driver), _OWNER, EntityInput(name="Acme", kind="org")
    )

    assert str(result.owner_id) == _NODE["owner_id"]
    assert result.name == "Acme"
    _, params = driver.calls[0]
    assert params["owner_id"] == _OWNER
    assert params["visibility"] == "private"
    assert params["attributes"] == "{}"
    assert params["id"] != ""  # a generated UUID string


async def test_list_graph_passes_owner_and_maps_every_row() -> None:
    driver = FakeNeo4jDriver([{"e": _NODE}, {"e": {**_NODE, "id": str(uuid4()), "name": "Beta"}}])

    view = await service.list_graph(cast(AsyncDriver, driver), _OWNER)

    assert [e.name for e in view.entities] == ["Acme", "Beta"]
    assert driver.calls[0][1] == {"owner_id": _OWNER}
