"""The LangGraph nodes, one module per stage.

Each node is ``async def <name>_node(state, *, deps) -> dict[str, Any]`` and
returns a partial update LangGraph merges into the state. This package re-exports
the node callables (and the couple of helpers the tests reach for).
"""

from __future__ import annotations

from app.agent.nodes._common import format_digest, format_documents, text_of
from app.agent.nodes.analyze import analyze_one_node, synthesize_node
from app.agent.nodes.commit import commit_node
from app.agent.nodes.enrich import enrich_node
from app.agent.nodes.lookup import lookup_node
from app.agent.nodes.plan import plan_node
from app.agent.nodes.search import (
    _parse_search_result,
    broaden_queries_node,
    fetch_node,
    search_node,
)
from app.agent.nodes.structure import critique_node, structure_node
from app.agent.nodes.survey import survey_graph_node

# Back-compat alias for the tests that used the old flat module.
_text = text_of

__all__ = [
    "_parse_search_result",
    "_text",
    "analyze_one_node",
    "broaden_queries_node",
    "commit_node",
    "critique_node",
    "enrich_node",
    "fetch_node",
    "format_digest",
    "format_documents",
    "lookup_node",
    "plan_node",
    "search_node",
    "structure_node",
    "survey_graph_node",
    "synthesize_node",
    "text_of",
]
