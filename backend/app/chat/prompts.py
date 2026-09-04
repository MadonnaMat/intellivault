"""Loader for the chat endpoint's system prompt.

Prompt text lives as Markdown under ``app/chat/prompts/`` — same convention as
``app/agent/prompts.py``, duplicated here rather than shared so ``app/chat``
stays a self-contained, import-cheap package.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

_PROMPT_DIR = Path(__file__).parent / "prompts"


@cache
def prompt(name: str) -> str:
    """Return the contents of ``app/chat/prompts/<name>.md`` (trailing WS stripped)."""
    return (_PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8").strip()
