"""The tools the chat model can call: check the existing knowledge graph, or
launch the background research agent to build on it.
"""

from __future__ import annotations

from typing import Any

SEARCH_KNOWLEDGE_GRAPH = "search_knowledge_graph"

SEARCH_KNOWLEDGE_GRAPH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": SEARCH_KNOWLEDGE_GRAPH,
        "description": (
            "Search the caller's existing knowledge graph (their own private entities "
            "plus everyone's public ones) for anything already known about a topic. "
            "Call this before launch_research_agent to check whether the graph already "
            "answers the question, so a new research run isn't launched unnecessarily."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for, at least 3 characters.",
                },
            },
            "required": ["query"],
        },
    },
}

LAUNCH_RESEARCH_AGENT = "launch_research_agent"

LAUNCH_RESEARCH_AGENT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": LAUNCH_RESEARCH_AGENT,
        "description": (
            "Launch a background research agent that investigates a topic in depth "
            "and adds its findings to the caller's private knowledge graph. Prefer "
            "search_knowledge_graph first — only launch when the graph doesn't already "
            "have what's needed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The research topic, at least 3 characters.",
                },
            },
            "required": ["topic"],
        },
    },
}
