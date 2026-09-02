"""Loader for the graph package's Cypher.

Multi-line statements live as files under ``app/graph/cypher/`` and are embedded
at first use — the same convention as ``app/auth/sql/`` for Postgres. Never
inline a multi-line Cypher string at the call site.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

_CYPHER_DIR = Path(__file__).parent / "cypher"


@cache
def cypher(name: str) -> str:
    """Return the contents of ``app/graph/cypher/<name>.cypher``."""
    return (_CYPHER_DIR / f"{name}.cypher").read_text(encoding="utf-8")
