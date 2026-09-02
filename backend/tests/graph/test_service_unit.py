"""Unit tests for app.graph.service — record→model mapping, no Neo4j."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from neo4j import AsyncDriver

from app.graph import service
from app.graph.schemas import EntityInput, RelationshipInput, VisibilityChange
from app.graph.service import _dt, _entity
from tests.graph.conftest import FakeNeo4jDriver

_OWNER = str(uuid4())
_FROM = str(uuid4())
_TO = str(uuid4())
_REL = {
    "id": str(uuid4()),
    "owner_id": _OWNER,
    "kind": "employs",
    "visibility": "private",
    "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
}
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


async def test_list_graph_passes_owner_and_maps_entities_and_edges() -> None:
    driver = FakeNeo4jDriver(
        [{"e": _NODE}, {"e": {**_NODE, "id": str(uuid4()), "name": "Beta"}}],
        [{"r": _REL, "from_id": _FROM, "to_id": _TO}],
    )

    view = await service.list_graph(cast(AsyncDriver, driver), _OWNER)

    assert [e.name for e in view.entities] == ["Acme", "Beta"]
    assert [r.kind for r in view.relationships] == ["employs"]
    assert driver.calls[0][1] == {"owner_id": _OWNER}
    assert driver.calls[1][1] == {"owner_id": _OWNER}


async def test_create_relationship_serialises_and_maps() -> None:
    driver = FakeNeo4jDriver([{"r": _REL, "from_id": _FROM, "to_id": _TO}])

    result = await service.create_relationship(
        cast(AsyncDriver, driver),
        _OWNER,
        RelationshipInput(from_id=_FROM, to_id=_TO, kind="employs"),
    )

    assert str(result.from_id) == _FROM
    assert str(result.to_id) == _TO
    assert result.kind == "employs"
    _, params = driver.calls[0]
    assert params["from_id"] == _FROM
    assert params["owner_id"] == _OWNER


async def test_create_relationship_404_when_endpoint_not_visible() -> None:
    driver = FakeNeo4jDriver([])  # the MATCH / ownership WHERE found nothing

    with pytest.raises(HTTPException) as exc:
        await service.create_relationship(
            cast(AsyncDriver, driver),
            _OWNER,
            RelationshipInput(from_id=_FROM, to_id=_TO, kind="x"),
        )

    assert exc.value.status_code == 404


async def test_delete_entity_ok_and_404() -> None:
    await service.delete_entity(cast(AsyncDriver, FakeNeo4jDriver([{"id": "e1"}])), _OWNER, "e1")

    with pytest.raises(HTTPException) as exc:
        await service.delete_entity(cast(AsyncDriver, FakeNeo4jDriver([])), _OWNER, "e1")
    assert exc.value.status_code == 404


async def test_delete_relationship_ok_and_404() -> None:
    await service.delete_relationship(
        cast(AsyncDriver, FakeNeo4jDriver([{"id": "r1"}])), _OWNER, "r1"
    )

    with pytest.raises(HTTPException) as exc:
        await service.delete_relationship(cast(AsyncDriver, FakeNeo4jDriver([])), _OWNER, "r1")
    assert exc.value.status_code == 404


async def test_change_visibility_single_flip() -> None:
    node_id = str(uuid4())
    driver = FakeNeo4jDriver([{"id": node_id}])

    result = await service.change_visibility(
        cast(AsyncDriver, driver), _OWNER, node_id, VisibilityChange(visibility="public")
    )

    assert [str(i) for i in result.affected_ids] == [node_id]
    assert driver.calls[0][1] == {"id": node_id, "owner_id": _OWNER, "visibility": "public"}


async def test_change_visibility_single_flip_404() -> None:
    driver = FakeNeo4jDriver([])

    with pytest.raises(HTTPException) as exc:
        await service.change_visibility(
            cast(AsyncDriver, driver), _OWNER, str(uuid4()), VisibilityChange(visibility="public")
        )

    assert exc.value.status_code == 404


async def test_change_visibility_cascade_flips_nodes_then_edges() -> None:
    ids = [str(uuid4()), str(uuid4())]
    driver = FakeNeo4jDriver([{"affected_ids": ids}], [{"updated": 1}])

    result = await service.change_visibility(
        cast(AsyncDriver, driver),
        _OWNER,
        ids[0],
        VisibilityChange(visibility="public", cascade=True),
    )

    assert [str(i) for i in result.affected_ids] == ids
    assert driver.calls[1][1] == {"ids": ids, "owner_id": _OWNER, "visibility": "public"}


async def test_change_visibility_cascade_404_when_start_missing() -> None:
    driver = FakeNeo4jDriver([])  # start node didn't match

    with pytest.raises(HTTPException) as exc:
        await service.change_visibility(
            cast(AsyncDriver, driver),
            _OWNER,
            str(uuid4()),
            VisibilityChange(visibility="public", cascade=True),
        )

    assert exc.value.status_code == 404
