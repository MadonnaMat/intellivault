"""app.agent.broker — broker selection, worker lifecycle events, span middleware."""

from __future__ import annotations

from typing import Any

import pytest
from taskiq import InMemoryBroker
from taskiq_redis import ListQueueBroker

from app.agent import broker as broker_mod
from app.agent.broker import AgentRunSpanMiddleware, build_broker
from app.config import Settings


def _settings(**extra: str) -> Settings:
    base = {"NEO4J_PASSWORD": "n", "DATABASE_URL": "postgresql://u:p@localhost:5432/db"}
    return Settings(_env_file=None, **{**base, **extra})  # type: ignore[arg-type]


def test_build_broker_picks_in_memory_for_memory_url() -> None:
    assert isinstance(build_broker(_settings(REDIS_URL="memory://")), InMemoryBroker)


def test_build_broker_picks_redis_for_a_real_url() -> None:
    assert isinstance(build_broker(_settings(REDIS_URL="redis://redis:6379/0")), ListQueueBroker)


def test_redis_broker_uses_a_blocking_read_timeout() -> None:
    """redis-py 8.1 defaults socket_timeout to 5s, which crashes the worker's
    blocking BRPOP — build_broker must pin it back to None."""
    broker = build_broker(_settings(REDIS_URL="redis://redis:6379/0"))
    conn = broker.connection_pool.make_connection()  # type: ignore[attr-defined]
    assert conn.socket_timeout is None
    assert conn.socket_connect_timeout == 15


def test_redis_broker_has_a_result_backend() -> None:
    """search_knowledge_graph_task's .wait_result() needs somewhere to poll —
    see app.chat.graph_search."""
    from taskiq_redis import RedisAsyncResultBackend

    broker = build_broker(_settings(REDIS_URL="redis://redis:6379/0"))
    assert isinstance(broker.result_backend, RedisAsyncResultBackend)


def _admin_middlewares(broker: object) -> list[object]:
    from taskiq.middlewares.taskiq_admin_middleware import TaskiqAdminMiddleware

    return [m for m in getattr(broker, "middlewares", []) if isinstance(m, TaskiqAdminMiddleware)]


def test_no_admin_middleware_without_a_configured_url() -> None:
    broker = build_broker(_settings(REDIS_URL="redis://redis:6379/0"))
    assert _admin_middlewares(broker) == []


def test_admin_middleware_added_when_url_is_configured() -> None:
    broker = build_broker(
        _settings(
            REDIS_URL="redis://redis:6379/0",
            TASKIQ_ADMIN_URL="http://taskiq-admin:3000",
            TASKIQ_ADMIN_TOKEN="secret",
        )
    )
    added = _admin_middlewares(broker)
    assert len(added) == 1
    assert getattr(added[0], "url", None) == "http://taskiq-admin:3000"


async def test_startup_builds_infra_and_shutdown_closes_it(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[str] = []

    class _Infra:
        async def aclose(self) -> None:
            closed.append("closed")

    async def _fake_build(_settings: Settings) -> _Infra:
        return _Infra()

    provider = _Provider()
    monkeypatch.setattr("app.agent.deps.build_worker_infra", _fake_build)
    monkeypatch.setattr("app.agent.broker.observability.setup_worker", lambda _s: provider)

    state: Any = broker_mod.broker.state
    await broker_mod._on_startup(state)  # type: ignore[misc]
    assert state.tracer_provider is provider
    assert isinstance(state.infra, _Infra)

    await broker_mod._on_shutdown(state)  # type: ignore[misc]
    assert closed == ["closed"]


async def test_shutdown_flushes_the_tracer_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    flushed: list[str] = []
    provider = type("P", (), {"shutdown": lambda self: flushed.append("shutdown")})()
    monkeypatch.setattr("app.agent.deps.build_worker_infra", lambda _s: _async_none())
    monkeypatch.setattr("app.agent.broker.observability.setup_worker", lambda _s: provider)

    state: Any = broker_mod.broker.state
    await broker_mod._on_startup(state)  # type: ignore[misc]
    await broker_mod._on_shutdown(state)  # type: ignore[misc]
    assert flushed == ["shutdown"]


async def _async_none() -> None:
    return None


async def test_shutdown_without_infra_is_a_noop() -> None:
    bare: Any = type("S", (), {})()
    await broker_mod._on_shutdown(bare)  # type: ignore[misc]


class _Span:
    def __init__(self) -> None:
        self.ended = False
        self.attrs: dict[str, Any] = {}
        self.exceptions: list[BaseException] = []

    def set_attribute(self, key: str, value: Any) -> None:
        self.attrs[key] = value

    def record_exception(self, exc: BaseException) -> None:
        self.exceptions.append(exc)

    def end(self) -> None:
        self.ended = True


class _Tracer:
    def __init__(self) -> None:
        self.span = _Span()
        self.opened: list[tuple[str, dict[str, Any]]] = []

    def start_span(self, name: str, attributes: dict[str, Any] | None = None) -> _Span:
        self.opened.append((name, attributes or {}))
        return self.span


class _Provider:
    def __init__(self) -> None:
        self.tracer = _Tracer()
        self.flushes = 0

    def get_tracer(self, _name: str) -> _Tracer:
        return self.tracer

    def force_flush(self, *_a: Any) -> None:
        self.flushes += 1

    def shutdown(self) -> None:
        self.flushes += 1


class _Msg:
    task_id = "t1"
    task_name = "run_agent"
    args: tuple[Any, ...] = ("run-1",)
    kwargs: dict[str, Any] = {}


def _middleware(provider: Any) -> AgentRunSpanMiddleware:
    mw = AgentRunSpanMiddleware()

    class _Broker:
        state = type("S", (), {"tracer_provider": provider})()

    mw.set_broker(_Broker())  # type: ignore[arg-type]
    return mw


def test_span_middleware_is_a_noop_without_a_provider() -> None:
    mw = _middleware(None)
    mw.pre_execute(_Msg())  # type: ignore[arg-type]
    mw.post_execute(_Msg(), object())  # type: ignore[arg-type]
    mw.on_error(_Msg(), object(), RuntimeError("x"))  # type: ignore[arg-type]


def test_span_middleware_flags_an_errored_result() -> None:
    provider = _Provider()
    mw = _middleware(provider)
    mw.pre_execute(_Msg())  # type: ignore[arg-type]
    mw.post_execute(_Msg(), type("R", (), {"is_err": True})())  # type: ignore[arg-type]
    assert provider.tracer.span.attrs["error"] is True
    assert provider.tracer.span.ended is True


def test_span_middleware_opens_closes_and_flushes() -> None:
    provider = _Provider()
    mw = _middleware(provider)
    mw.pre_execute(_Msg())  # type: ignore[arg-type]
    mw.post_execute(_Msg(), type("R", (), {"is_err": False})())  # type: ignore[arg-type]
    assert provider.tracer.span.ended is True
    assert provider.flushes == 1  # the run's spans are pushed to Phoenix immediately


def test_span_middleware_records_an_error() -> None:
    provider = _Provider()
    mw = _middleware(provider)
    mw.pre_execute(_Msg())  # type: ignore[arg-type]
    boom = RuntimeError("boom")
    mw.on_error(_Msg(), object(), boom)  # type: ignore[arg-type]
    assert provider.tracer.span.exceptions == [boom]
    assert provider.tracer.span.attrs["error"] is True


def test_span_is_named_for_the_task_not_a_blanket_agent_run() -> None:
    from openinference.semconv.trace import SpanAttributes

    provider = _Provider()
    mw = _middleware(provider)

    class _SearchMsg(_Msg):
        task_name = "search_knowledge_graph_task"
        args = ("owner-1", "transistor", 5)

    mw.pre_execute(_SearchMsg())  # type: ignore[arg-type]

    name, attributes = provider.tracer.opened[0]
    assert name == "search_knowledge_graph_task"
    assert attributes[SpanAttributes.OPENINFERENCE_SPAN_KIND] == "CHAIN"
    assert '"transistor"' in attributes[SpanAttributes.METADATA]


def test_run_agent_span_kind_is_agent() -> None:
    from openinference.semconv.trace import SpanAttributes

    provider = _Provider()
    mw = _middleware(provider)
    mw.pre_execute(_Msg())  # type: ignore[arg-type]

    name, attributes = provider.tracer.opened[0]
    assert name == "run_agent"
    assert attributes[SpanAttributes.OPENINFERENCE_SPAN_KIND] == "AGENT"


def test_post_execute_captures_the_return_value_as_output() -> None:
    from openinference.semconv.trace import SpanAttributes

    provider = _Provider()
    mw = _middleware(provider)
    mw.pre_execute(_Msg())  # type: ignore[arg-type]
    result = type("R", (), {"is_err": False, "return_value": {"entities": ["Bell Labs"]}})()

    mw.post_execute(_Msg(), result)  # type: ignore[arg-type]

    assert '"Bell Labs"' in provider.tracer.span.attrs[SpanAttributes.OUTPUT_VALUE]


def test_post_execute_skips_output_when_return_value_is_none() -> None:
    provider = _Provider()
    mw = _middleware(provider)
    mw.pre_execute(_Msg())  # type: ignore[arg-type]
    result = type("R", (), {"is_err": False, "return_value": None})()

    mw.post_execute(_Msg(), result)  # type: ignore[arg-type]

    from openinference.semconv.trace import SpanAttributes

    assert SpanAttributes.OUTPUT_VALUE not in provider.tracer.span.attrs
