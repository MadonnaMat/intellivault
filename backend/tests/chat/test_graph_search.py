"""app.chat.graph_search — the search_knowledge_graph tool's execution."""

from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

import httpx
import pytest
from neo4j import AsyncDriver

from app.chat import graph_search, ollama_client
from app.graph import service as graph_service
from app.graph.schemas import Entity, Relationship
from tests.chat.conftest import make_settings, now

_CLIENT = cast(httpx.AsyncClient, None)
_DRIVER = cast(AsyncDriver, None)
_OWNER = str(uuid4())


def _entity(name: str, kind: str = "org") -> Entity:
    return Entity(
        id=uuid4(),
        owner_id=uuid4(),
        visibility="private",
        name=name,
        kind=kind,
        attributes={},
        created_at=now(),
        updated_at=now(),
    )


def _relationship(from_id: UUID, to_id: UUID, kind: str = "employs") -> Relationship:
    return Relationship(
        id=uuid4(),
        owner_id=uuid4(),
        from_id=from_id,
        to_id=to_id,
        kind=kind,
        visibility="private",
        created_at=now(),
        updated_at=now(),
    )


async def test_search_knowledge_graph_embeds_then_searches_then_fetches_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bell_labs = _entity("Bell Labs")
    shockley = _entity("Shockley")
    edge = _relationship(bell_labs.id, shockley.id)

    async def fake_embed(client: object, settings: object, text: str) -> list[float]:
        assert text == "the transistor"
        return [0.1, 0.2]

    async def fake_search(
        driver: object, owner_id: str, embedding: list[float], k: int
    ) -> list[Entity]:
        assert owner_id == _OWNER
        assert embedding == [0.1, 0.2]
        assert k == make_settings().chat_search_max_entities
        return [bell_labs, shockley]

    async def fake_edges(
        driver: object, owner_id: str, entity_ids: list[str]
    ) -> list[Relationship]:
        assert set(entity_ids) == {str(bell_labs.id), str(shockley.id)}
        return [edge]

    monkeypatch.setattr(ollama_client, "embed_query", fake_embed)
    monkeypatch.setattr(graph_service, "search_entities_by_vector", fake_search)
    monkeypatch.setattr(graph_service, "list_visible_relationships_among", fake_edges)

    entities, relationships = await graph_search.search_knowledge_graph(
        _DRIVER, _CLIENT, make_settings(), _OWNER, "the transistor"
    )

    assert entities == [bell_labs, shockley]
    assert relationships == [edge]


async def test_search_knowledge_graph_short_circuits_on_no_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    edges_called = False

    async def fake_embed(client: object, settings: object, text: str) -> list[float]:
        return [0.1]

    async def fake_search(*args: object, **kwargs: object) -> list[Entity]:
        return []

    async def fake_edges(*args: object, **kwargs: object) -> list[Relationship]:
        nonlocal edges_called
        edges_called = True
        return []

    monkeypatch.setattr(ollama_client, "embed_query", fake_embed)
    monkeypatch.setattr(graph_service, "search_entities_by_vector", fake_search)
    monkeypatch.setattr(graph_service, "list_visible_relationships_among", fake_edges)

    entities, relationships = await graph_search.search_knowledge_graph(
        _DRIVER, _CLIENT, make_settings(), _OWNER, "nothing here"
    )

    assert entities == []
    assert relationships == []
    assert edges_called is False  # bounded: no edge lookup when there's nothing to bound it to


def test_format_search_result_lists_entities_and_relationships() -> None:
    bell_labs = _entity("Bell Labs")
    shockley = _entity("Shockley", kind="person")
    edge = _relationship(bell_labs.id, shockley.id, kind="employs")

    text = graph_search.format_search_result([bell_labs, shockley], [edge])

    assert "- Bell Labs (org)" in text
    assert "- Shockley (person)" in text
    assert "Bell Labs -[employs]-> Shockley" in text


def test_format_search_result_empty() -> None:
    assert (
        graph_search.format_search_result([], [])
        == "No matching entities found in the knowledge graph."
    )
