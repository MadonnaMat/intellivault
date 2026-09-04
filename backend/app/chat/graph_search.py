"""Executes the ``search_knowledge_graph`` tool by handing it to the worker.

The actual search runs as a small LangGraph (``app.agent.search_graph``) —
vector search with a lexical fallback, then the edges among the hits — so it
can branch on what it finds, the same way the research agent's own nodes do.
That means it must run in the worker process, not here: this module only
enqueues ``search_knowledge_graph_task`` and waits for its result, exactly
like ``app.agent.service.enqueue_run`` hands the research agent to the worker
— imported lazily so this stays out of the gateway's import path
(``tests/agent/test_imports.py``).
"""

from __future__ import annotations

from app.config import Settings
from app.graph.schemas import Entity, Relationship


async def search_knowledge_graph(
    settings: Settings, owner_id: str, query: str
) -> tuple[list[Entity], list[Relationship], str | None]:
    """Enqueue the search graph and wait (bounded by
    ``settings.chat_search_timeout``) for its result."""
    from taskiq import TaskiqResultTimeoutError

    from app.agent.tasks import search_knowledge_graph_task

    task = await search_knowledge_graph_task.kiq(owner_id, query, settings.chat_search_max_entities)
    try:
        result = await task.wait_result(timeout=settings.chat_search_timeout)
    except TaskiqResultTimeoutError:
        return [], [], "search timed out"
    if result.is_err:
        return [], [], f"search failed: {result.error}"
    data = result.return_value
    entities = [Entity.model_validate(e) for e in data["entities"]]
    relationships = [Relationship.model_validate(r) for r in data["relationships"]]
    return entities, relationships, data.get("note")


def format_search_result(
    entities: list[Entity], relationships: list[Relationship], note: str | None
) -> str:
    """Compact text digest fed back to the model as the tool's result."""
    if not entities:
        return note or "No matching entities found in the knowledge graph."
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
