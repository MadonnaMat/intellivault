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


def test_get_provider_reads_app_state() -> None:
    app = FastAPI()
    assert observability.get_provider(app) is None
    sentinel = object()
    app.state.tracer_provider = sentinel
    assert observability.get_provider(app) is sentinel


def test_traced_is_a_noop_without_a_provider() -> None:
    with observability.traced(None, "app.chat", "chat.turn", kind="AGENT") as span:
        assert span is None


def test_traced_opens_a_span_with_openinference_attributes() -> None:
    from openinference.semconv.trace import SpanAttributes

    class _FakeSpan:
        def __init__(self) -> None:
            self.attrs: dict[str, object] = {}

        def set_attribute(self, key: str, value: object) -> None:
            self.attrs[key] = value

    class _FakeTracer:
        def __init__(self) -> None:
            self.opened: list[tuple[str, dict[str, object]]] = []
            self.span = _FakeSpan()

        def start_as_current_span(self, name: str, attributes: dict[str, object] | None = None):  # type: ignore[no-untyped-def]
            from contextlib import contextmanager

            @contextmanager
            def _cm():  # type: ignore[no-untyped-def]
                self.opened.append((name, attributes or {}))
                yield self.span

            return _cm()

    class _FakeProvider:
        def __init__(self) -> None:
            self.tracer = _FakeTracer()

        def get_tracer(self, _name: str) -> _FakeTracer:
            return self.tracer

    provider = _FakeProvider()
    with observability.traced(
        provider, "app.chat", "chat.turn", kind="AGENT", metadata={"user_id": "u1"}
    ) as span:
        assert span is provider.tracer.span

    name, attributes = provider.tracer.opened[0]
    assert name == "chat.turn"
    assert attributes[SpanAttributes.OPENINFERENCE_SPAN_KIND] == "AGENT"
    assert '"user_id": "u1"' in str(attributes[SpanAttributes.METADATA])


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
