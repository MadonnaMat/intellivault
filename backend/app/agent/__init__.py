"""The agent loop: a LangGraph research agent, enqueued here, run by a worker.

This package's ``__init__`` stays import-cheap — only the router — so importing
the FastAPI gateway never pulls in langgraph / langchain. The worker imports
``app.agent.tasks`` (and through it ``graph``/``nodes``) explicitly.
"""

from __future__ import annotations

from app.agent.router import router as agent_router

__all__ = ["agent_router"]
