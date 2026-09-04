"""Ollama passthrough chat, with tool-calling to launch the background agent.

This package's ``__init__`` stays import-cheap — only the router.
"""

from __future__ import annotations

from app.chat.router import router as chat_router

__all__ = ["chat_router"]
