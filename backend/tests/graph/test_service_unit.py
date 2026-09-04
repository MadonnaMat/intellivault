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


async def test_list_graph_maps_sources_onto_entities() -> None:
    driver = FakeNeo4jDriver(
        [{"e": _NODE, "sources": ["https://a.example/x", "https://b.example/y"]}],
        [],
    )

    view = await service.list_graph(cast(AsyncDriver, driver), _OWNER)

    assert view.entities[0].sources == ["https://a.example/x", "https://b.example/y"]


async def test_attach_sources_sends_owner_entity_and_urls() -> None:
    driver = FakeNeo4jDriver([])
    entity_id = str(uuid4())
    urls = ["https://a.example/x", "https://b.example/y"]

    await service.attach_sources(cast(AsyncDriver, driver), _OWNER, entity_id, urls)

    query, params = driver.calls[0]
    assert "SOURCED_FROM" in query
    assert params == {"owner_id": _OWNER, "entity_id": entity_id, "urls": urls}


async def test_attach_sources_short_circuits_on_no_urls() -> None:
    driver = FakeNeo4jDriver([])
    await service.attach_sources(cast(AsyncDriver, driver), _OWNER, str(uuid4()), [])
    assert driver.calls == []


async def test_list_visible_relationships_among_passes_ids_and_owner() -> None:
    driver = FakeNeo4jDriver([{"r": _REL, "from_id": _FROM, "to_id": _TO}])
    ids = [str(_FROM), str(_TO)]

    rels = await service.list_visible_relationships_among(cast(AsyncDriver, driver), _OWNER, ids)

    assert [r.kind for r in rels] == ["employs"]
    assert driver.calls[0][1] == {"owner_id": _OWNER, "ids": ids}


async def test_list_visible_relationships_among_short_circuits_on_no_ids() -> None:
    driver = FakeNeo4jDriver([])
    rels = await service.list_visible_relationships_among(cast(AsyncDriver, driver), _OWNER, [])
    assert rels == []
    assert driver.calls == []


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
    driver = FakeNeo4jDriver([], [])  # create: no row; diagnostic: no row either

    with pytest.raises(HTTPException) as exc:
        await service.create_relationship(
            cast(AsyncDriver, driver),
            _OWNER,
            RelationshipInput(from_id=_FROM, to_id=_TO, kind="x"),
        )

    assert exc.value.status_code == 404


async def test_create_relationship_422_for_a_public_edge_to_a_private_endpoint() -> None:
    driver = FakeNeo4jDriver(
        [],  # create: rejected by the visibility rule
        [{"from_visibility": "public", "to_visibility": "private"}],  # diagnostic
    )

    with pytest.raises(HTTPException) as exc:
        await service.create_relationship(
            cast(AsyncDriver, driver),
            _OWNER,
            RelationshipInput(from_id=_FROM, to_id=_TO, kind="x", visibility="public"),
        )

    assert exc.value.status_code == 422


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


async def test_change_visibility_single_flip_reports_the_change() -> None:
    node_id = str(uuid4())
    driver = FakeNeo4jDriver([{"id": node_id, "changed": True}])

    result = await service.change_visibility(
        cast(AsyncDriver, driver), _OWNER, node_id, VisibilityChange(visibility="public")
    )

    assert [str(i) for i in result.affected_ids] == [node_id]
    assert driver.calls[0][1] == {"id": node_id, "owner_id": _OWNER, "visibility": "public"}


async def test_change_visibility_single_flip_noop_reports_nothing() -> None:
    driver = FakeNeo4jDriver([{"id": str(uuid4()), "changed": False}])

    result = await service.change_visibility(
        cast(AsyncDriver, driver), _OWNER, str(uuid4()), VisibilityChange(visibility="public")
    )

    assert result.affected_ids == []


async def test_change_visibility_single_flip_404() -> None:
    driver = FakeNeo4jDriver([])

    with pytest.raises(HTTPException) as exc:
        await service.change_visibility(
            cast(AsyncDriver, driver), _OWNER, str(uuid4()), VisibilityChange(visibility="public")
        )

    assert exc.value.status_code == 404


async def test_change_visibility_to_private_cleans_incident_edges() -> None:
    node_id = str(uuid4())
    driver = FakeNeo4jDriver(
        [{"id": node_id, "changed": True}],  # set_entity_visibility
        [],  # sync_entity_sources (return value unused)
        [{"changed": 0}],  # demote_owned_edges
        [{"removed": 2}],  # remove_foreign_edges
    )

    result = await service.change_visibility(
        cast(AsyncDriver, driver), _OWNER, node_id, VisibilityChange(visibility="private")
    )

    assert [str(i) for i in result.affected_ids] == [node_id]
    assert any("DELETE r" in text for text, _ in driver.calls)  # remove_foreign_edges ran
    # sync_entity_sources, demote_owned_edges, remove_foreign_edges all key off ids=[node_id].
    assert sum(1 for _, params in driver.calls if params.get("ids") == [node_id]) == 3


async def test_change_visibility_single_flip_syncs_sources() -> None:
    node_id = str(uuid4())
    driver = FakeNeo4jDriver([{"id": node_id, "changed": True}])

    await service.change_visibility(
        cast(AsyncDriver, driver), _OWNER, node_id, VisibilityChange(visibility="public")
    )

    query, params = driver.calls[1]
    assert "sync_entity_sources" not in query  # the file's contents, not its name, are recorded
    assert "SOURCED_FROM" in query
    assert params == {"ids": [node_id], "owner_id": _OWNER}


async def test_change_visibility_single_flip_noop_does_not_sync_sources() -> None:
    driver = FakeNeo4jDriver([{"id": str(uuid4()), "changed": False}])

    await service.change_visibility(
        cast(AsyncDriver, driver), _OWNER, str(uuid4()), VisibilityChange(visibility="public")
    )

    assert len(driver.calls) == 1  # only set_entity_visibility ran


async def test_change_visibility_cascade_syncs_sources_for_all_changed() -> None:
    start, neighbour = str(uuid4()), str(uuid4())
    driver = FakeNeo4jDriver(
        [{"id": start}],  # owned_entity_exists
        [{"id": neighbour}],  # owned_neighbours of {start}
        [],  # owned_neighbours of {neighbour} — BFS stops
        [{"changed": [start, neighbour]}],  # flip_entities
        [{"changed": 1}],  # flip_relationships
    )

    await service.change_visibility(
        cast(AsyncDriver, driver),
        _OWNER,
        start,
        VisibilityChange(visibility="public", cascade=True),
    )

    # calls: 0 owned_entity_exists, 1-2 owned_neighbours, 3 flip_entities,
    # 4 flip_relationships, 5 sync_entity_sources.
    query, params = driver.calls[5]
    assert "SOURCED_FROM" in query
    assert set(cast(list[str], params["ids"])) == {start, neighbour}
    assert params["owner_id"] == _OWNER


async def test_change_visibility_cascade_bfs_then_flips_only_changed() -> None:
    start, neighbour = str(uuid4()), str(uuid4())
    driver = FakeNeo4jDriver(
        [{"id": start}],  # owned_entity_exists
        [{"id": neighbour}],  # owned_neighbours of {start}
        [],  # owned_neighbours of {neighbour} — BFS stops
        [{"changed": [start, neighbour]}],  # flip_entities
        [{"changed": 1}],  # flip_relationships
    )

    result = await service.change_visibility(
        cast(AsyncDriver, driver),
        _OWNER,
        start,
        VisibilityChange(visibility="public", cascade=True),
    )

    assert {str(i) for i in result.affected_ids} == {start, neighbour}
    # calls: 0 owned_entity_exists, 1-2 owned_neighbours, 3 flip_entities, 4 flip_relationships
    flip_ids = cast(list[str], driver.calls[3][1]["ids"])
    assert set(flip_ids) == {start, neighbour}
    assert driver.calls[4][1]["ids"] == flip_ids


async def test_change_visibility_cascade_404_when_start_not_owned() -> None:
    driver = FakeNeo4jDriver([])  # owned_entity_exists empty

    with pytest.raises(HTTPException) as exc:
        await service.change_visibility(
            cast(AsyncDriver, driver),
            _OWNER,
            str(uuid4()),
            VisibilityChange(visibility="public", cascade=True),
        )

    assert exc.value.status_code == 404


async def test_set_entity_embedding_sends_owner_scoped_params() -> None:
    entity_id = str(uuid4())
    driver = FakeNeo4jDriver([{"id": entity_id}])
    vec = [0.1, 0.2, 0.3]
    await service.set_entity_embedding(cast(AsyncDriver, driver), _OWNER, entity_id, vec)

    query, params = driver.calls[0]
    assert "SET e.embedding = $embedding" in query
    assert params == {"id": entity_id, "owner_id": _OWNER, "embedding": vec}


async def test_set_entity_embedding_404_when_not_owned() -> None:
    driver = FakeNeo4jDriver([])  # nothing matched the owner-scoped pattern
    with pytest.raises(HTTPException) as exc:
        await service.set_entity_embedding(cast(AsyncDriver, driver), _OWNER, str(uuid4()), [0.0])
    assert exc.value.status_code == 404


async def test_search_entities_by_vector_maps_nodes_and_passes_k() -> None:
    driver = FakeNeo4jDriver([{"e": _NODE, "score": 0.9}])
    results = await service.search_entities_by_vector(
        cast(AsyncDriver, driver), _OWNER, [0.1, 0.2], k=5
    )

    assert [e.name for e in results] == ["Acme"]
    _query, params = driver.calls[0]
    assert params == {"owner_id": _OWNER, "embedding": [0.1, 0.2], "k": 5}
