"""Loader for the auth package's SQL.

Multi-line statements live as files under ``app/auth/sql/`` and are embedded at
first use; trivial one-line statements stay inline at the call site.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

_SQL_DIR = Path(__file__).parent / "sql"


@cache
def sql(name: str) -> str:
    """Return the contents of ``app/auth/sql/<name>.sql``."""
    return (_SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")
