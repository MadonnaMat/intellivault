"""Shared test fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

# Required config — set before any `app.config` import so Settings() validates.
os.environ.setdefault("NEO4J_PASSWORD", "test-neo4j-pw")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://intellivault:intellivault@localhost:5432/intellivault_test"
)


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Iterator[None]:
    """Ensure each test sees a freshly built Settings singleton."""
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
