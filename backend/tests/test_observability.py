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


def test_register_failure_is_swallowed(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If phoenix.otel.register blows up, setup logs and carries on.

    register() is patched to raise so the test never starts a real tracer
    provider / global httpx instrumentation (which would leak into other tests).
    """
    import phoenix.otel

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("no collector")

    monkeypatch.setattr(phoenix.otel, "register", boom)

    with caplog.at_level(logging.WARNING):
        observability.setup(FastAPI(), _settings(TRACING_ENABLED="true"))

    assert "instrumentation disabled" in caplog.text
