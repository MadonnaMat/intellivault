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


@pytest.fixture
def review_sql() -> str:
    return (MIGRATIONS / "0005.agent-run-review.sql").read_text(encoding="utf-8")


def test_review_widens_the_status_check(review_sql: str) -> None:
    collapsed = " ".join(review_sql.split())
    assert "DROP CONSTRAINT agent_runs_status_check" in collapsed
    assert (
        "CHECK (status IN ('queued', 'running', 'awaiting_review', "
        "'succeeded', 'failed', 'cancelled'))" in collapsed
    )


def test_review_adds_the_pending_column(review_sql: str) -> None:
    assert "ADD COLUMN pending JSONB" in review_sql


def test_review_rollback_restores_the_original_check() -> None:
    rollback = (MIGRATIONS / "0005.agent-run-review.rollback.sql").read_text(encoding="utf-8")
    collapsed = " ".join(rollback.split())
    assert "DROP COLUMN pending" in collapsed
    assert "CHECK (status IN ('queued', 'running', 'succeeded', 'failed'))" in collapsed


@pytest.fixture
def source_urls_sql() -> str:
    return (MIGRATIONS / "0006.agent-run-source-urls.sql").read_text(encoding="utf-8")


def test_adds_the_source_urls_column(source_urls_sql: str) -> None:
    assert "ADD COLUMN source_urls JSONB NOT NULL DEFAULT '[]'::jsonb" in source_urls_sql


def test_source_urls_rollback_drops_the_column() -> None:
    rollback = (MIGRATIONS / "0006.agent-run-source-urls.rollback.sql").read_text(encoding="utf-8")
    assert rollback.strip() == "ALTER TABLE agent_runs DROP COLUMN source_urls;"
