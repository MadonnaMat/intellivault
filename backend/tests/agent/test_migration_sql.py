"""Static checks on the agent_runs migration — runs without a database.

The apply/rollback round-trip is covered by tests/app/test_migrations.py (which
self-skips without TEST_DATABASE_URL); this just pins the shape of the schema.
"""

from __future__ import annotations

from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


@pytest.fixture
def sql() -> str:
    return (MIGRATIONS / "0004.agent-runs.sql").read_text(encoding="utf-8")


def test_creates_agent_runs_table(sql: str) -> None:
    assert "CREATE TABLE agent_runs" in sql


def test_user_id_is_a_cascading_fk(sql: str) -> None:
    assert "user_id" in sql
    assert "REFERENCES users (id) ON DELETE CASCADE" in sql


def test_status_is_constrained(sql: str) -> None:
    assert "CHECK (status IN ('queued', 'running', 'succeeded', 'failed'))" in sql


def test_committed_id_columns_default_empty(sql: str) -> None:
    collapsed = " ".join(sql.split())
    for column in ("committed_entity_ids", "committed_relationship_ids"):
        assert f"{column} UUID[] NOT NULL DEFAULT '{{}}'" in collapsed


def test_has_the_list_index(sql: str) -> None:
    collapsed = " ".join(sql.split())
    assert (
        "CREATE INDEX agent_runs_user_id_created_at_idx "
        "ON agent_runs (user_id, created_at DESC)" in collapsed
    )


def test_rollback_drops_the_table() -> None:
    rollback = (MIGRATIONS / "0004.agent-runs.rollback.sql").read_text(encoding="utf-8")
    assert rollback.strip() == "DROP TABLE agent_runs;"
