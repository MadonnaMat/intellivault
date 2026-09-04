"""The one tool the chat model can call: launch the background research agent."""

from __future__ import annotations

from typing import Any

LAUNCH_RESEARCH_AGENT = "launch_research_agent"

LAUNCH_RESEARCH_AGENT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": LAUNCH_RESEARCH_AGENT,
        "description": (
            "Launch a background research agent that investigates a topic in depth "
            "and adds its findings to the caller's private knowledge graph."
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
