"""The observability setup is best-effort and must never raise."""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI

from app import observability
from app.config import Settings

_BASE = {"NEO4J_PASSWORD": "x", "DATABASE_URL": "postgresql://u:p@localhost:5432/db"}


def _settings(**extra: str) -> Settings:
    return Settings(_env_file=None, **{**_BASE, **extra})  # type: ignore[arg-type]


def test_disabled_is_noop(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        observability.setup(FastAPI(), _settings(TRACING_ENABLED="false"))
    assert "skipping OTel/Phoenix setup" in caplog.text


def test_unreachable_endpoint_does_not_raise() -> None:
    # A syntactically valid but dead endpoint: register() must not propagate.
    observability.setup(
        FastAPI(),
        _settings(TRACING_ENABLED="true", PHOENIX_COLLECTOR_ENDPOINT="http://127.0.0.1:1"),
    )
