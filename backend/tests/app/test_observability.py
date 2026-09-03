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


def test_disabled_returns_none_and_is_a_noop(caplog: pytest.LogCaptureFixture) -> None:
    settings = _settings(TRACING_ENABLED="false")
    with caplog.at_level(logging.INFO):
        assert observability._register_tracer_provider(settings) is None
        observability.setup(FastAPI(), settings)
        assert observability.setup_worker(settings) is None
    assert "skipping OTel/Phoenix setup" in caplog.text


def test_register_failure_is_swallowed(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If phoenix.otel.register blows up, nothing raises and no tracer starts.

    register() is patched to raise so the test never starts a real tracer
    provider / global httpx instrumentation (which would leak into other tests).
    """
    import phoenix.otel

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("no collector")

    monkeypatch.setattr(phoenix.otel, "register", boom)

    with caplog.at_level(logging.WARNING):
        assert observability._register_tracer_provider(_settings(TRACING_ENABLED="true")) is None
        observability.setup(FastAPI(), _settings(TRACING_ENABLED="true"))
        assert observability.setup_worker(_settings(TRACING_ENABLED="true")) is None

    assert "register failed" in caplog.text


def test_setup_stashes_the_provider_on_app_state(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    monkeypatch.setattr(observability, "_register_tracer_provider", lambda _s: sentinel)

    class _NoopInstrumentor:
        def instrument_app(self, *_a: object, **_k: object) -> None: ...

        def instrument(self, *_a: object, **_k: object) -> None: ...

        def __call__(self) -> _NoopInstrumentor:
            return self

    import opentelemetry.instrumentation.fastapi as fa
    import opentelemetry.instrumentation.httpx as hx

    monkeypatch.setattr(fa, "FastAPIInstrumentor", _NoopInstrumentor())
    monkeypatch.setattr(hx, "HTTPXClientInstrumentor", _NoopInstrumentor())

    app = FastAPI()
    observability.setup(app, _settings(TRACING_ENABLED="true"))
    assert app.state.tracer_provider is sentinel


def test_setup_worker_returns_the_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    monkeypatch.setattr(observability, "_register_tracer_provider", lambda _s: sentinel)

    class _NoopInstrumentor:
        def instrument(self, *_a: object, **_k: object) -> None: ...

        def __call__(self) -> _NoopInstrumentor:
            return self

    import openinference.instrumentation.langchain as lc
    import opentelemetry.instrumentation.httpx as hx

    monkeypatch.setattr(lc, "LangChainInstrumentor", _NoopInstrumentor())
    monkeypatch.setattr(hx, "HTTPXClientInstrumentor", _NoopInstrumentor())

    assert observability.setup_worker(_settings(TRACING_ENABLED="true")) is sentinel
