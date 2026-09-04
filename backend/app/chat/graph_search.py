"""Executes the ``search_knowledge_graph`` tool: a bounded vector search over
the caller's own visible graph, so the chat model can check existing
knowledge before deciding whether a full research run is actually needed.
"""

from __future__ import annotations

import httpx
from neo4j import AsyncDriver

from app.chat import ollama_client
from app.config import Settings
from app.graph import service as graph_service
from app.graph.schemas import Entity, Relationship


async def search_knowledge_graph(
    driver: AsyncDriver,
    client: httpx.AsyncClient,
    settings: Settings,
    owner_id: str,
    query: str,
) -> tuple[list[Entity], list[Relationship]]:
    """The ``settings.chat_search_max_entities`` visible entities nearest
    ``query`` (own + public, by embedding), plus the visible edges among
    them — mirrors ``app.agent.nodes.survey``'s bounded vector digest."""
    vector = await ollama_client.embed_query(client, settings, query)
    entities = await graph_service.search_entities_by_vector(
        driver, owner_id, vector, settings.chat_search_max_entities
    )
    if not entities:
        return [], []
    ids = [str(e.id) for e in entities]
    relationships = await graph_service.list_visible_relationships_among(driver, owner_id, ids)
    return entities, relationships


def format_search_result(entities: list[Entity], relationships: list[Relationship]) -> str:
    """Compact text digest fed back to the model as the tool's result."""
    if not entities:
        return "No matching entities found in the knowledge graph."
    name_by_id = {str(e.id): e.name for e in entities}
    lines = [f"- {e.name} ({e.kind})" for e in entities]
    if relationships:
        lines.append("relationships:")
        lines += [
            f"  - {name_by_id.get(str(r.from_id), str(r.from_id))} "
            f"-[{r.kind}]-> {name_by_id.get(str(r.to_id), str(r.to_id))}"
            for r in relationships
        ]
    return "\n".join(lines)
