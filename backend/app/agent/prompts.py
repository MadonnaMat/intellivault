"""Loader for the agent's LLM prompts.

Prompt text lives as Markdown under ``app/agent/prompts/`` and is embedded at
first use — same convention as ``app/agent/sql/`` + ``app/agent/statements.py``.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

_PROMPT_DIR = Path(__file__).parent / "prompts"


@cache
def prompt(name: str) -> str:
    """Return the contents of ``app/agent/prompts/<name>.md`` (trailing WS stripped)."""
    return (_PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8").strip()
