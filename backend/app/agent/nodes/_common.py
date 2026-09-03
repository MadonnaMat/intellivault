"""Helpers shared across the node modules — prompt formatting, tokenisation."""

from __future__ import annotations

import re
from typing import Any

from app.agent.fetch import FetchedDoc
from app.agent.schemas import GraphDigest

_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> set[str]:
    """Lowercase alnum tokens longer than two chars."""
    return {t for t in _TOKEN.findall(text.lower()) if len(t) > 2}


def text_of(content: Any) -> str:
    """Flatten an LLM message ``content`` (str, or a list of parts) to a string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(part if isinstance(part, str) else str(part) for part in content)
    return str(content)


def format_documents(docs: list[FetchedDoc]) -> str:
    if not docs:
        return "(no sources were fetched)"
    return "\n\n".join(f"SOURCE {i} <{d.url}>\n{d.text}" for i, d in enumerate(docs, 1))


def format_digest(digest: GraphDigest | None) -> str:
    if digest is None or not digest.entities:
        return "(the existing graph is empty)"
    return "\n".join(f"- {e.name} [{e.kind}] id={e.id}" for e in digest.entities)
