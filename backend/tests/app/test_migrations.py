"""Integration test: migrations apply and roll back cleanly via the yoyo CLI.

Runs against TEST_DATABASE_URL (a dedicated database, never the app's) and
self-skips when that database is not reachable, so `make backend-test` stays
runnable without infrastructure.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://intellivault:intellivault@localhost:5432/intellivault_test",
)
BACKEND_DIR = Path(__file__).resolve().parents[2]
YOYO = shutil.which("yoyo")


def _yoyo(*args: str) -> subprocess.CompletedProcess[str]:
    assert YOYO is not None
    return subprocess.run(
        [YOYO, *args, "--batch", "--database", TEST_DATABASE_URL, "migrations"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=True,
    )


def _reachable() -> bool:
    if YOYO is None:
        return False
    try:
        _yoyo("list")
    except subprocess.CalledProcessError:
        return False
    return True


pytestmark = pytest.mark.skipif(not _reachable(), reason="TEST_DATABASE_URL not reachable")


@pytest.fixture
def clean_db() -> Iterator[None]:
    _yoyo("rollback", "--all")
    yield
    # Leave the schema in place — other suites (e.g. the auth e2e tests) share
    # this database and run after this one.
    _yoyo("apply")


def test_apply_then_rollback(clean_db: None) -> None:
    assert _yoyo("list").stdout.count("\nU ") >= 1  # nothing applied yet

    _yoyo("apply")
    applied = _yoyo("list").stdout
    assert "\nA " in applied and "0001.initial-schema" in applied
    assert "0002.auth-webauthn" in applied
    assert "0003.registration-challenge-and-indexes" in applied
    assert "0004.agent-runs" in applied
    assert "0005.agent-run-review" in applied

    _yoyo("rollback", "--all")
    assert _yoyo("list").stdout.count("\nA ") == 0
