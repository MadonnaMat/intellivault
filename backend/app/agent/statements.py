"""Loader for the agent package's SQL.

Multi-line statements live as files under ``app/agent/sql/`` and are embedded at
first use — mirrors ``app/auth/statements.py``.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

_SQL_DIR = Path(__file__).parent / "sql"


@cache
def sql(name: str) -> str:
    """Return the contents of ``app/agent/sql/<name>.sql``."""
    return (_SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")
