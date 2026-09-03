"""The taskiq broker + worker lifecycle for the agent loop.

Run the worker as its own process:

    taskiq worker app.agent.broker:broker app.agent.tasks \
        --workers 1 --max-async-tasks $AGENT_WORKER_CONCURRENCY

This module must **not** import ``app.agent.tasks`` (the worker CLI names it
explicitly) — that keeps ``broker`` importable from the gateway's enqueue path
without pulling in langgraph.
"""

from __future__ import annotations

from typing import Any

from taskiq import AsyncBroker, InMemoryBroker, TaskiqEvents, TaskiqMessage, TaskiqMiddleware
from taskiq.middlewares.taskiq_admin_middleware import TaskiqAdminMiddleware
from taskiq.state import TaskiqState
from taskiq_redis import ListQueueBroker

from app import observability
from app.config import Settings, get_settings

_MEMORY = "memory://"


def build_broker(settings: Settings) -> AsyncBroker:
    """A Redis-backed queue, or the in-process broker when ``redis_url`` is memory://.

    ``socket_timeout=None`` is load-bearing: redis-py 8.1 changed the default
    read timeout from "none" to 5s, but the worker's ``listen()`` issues a
    ``BRPOP key 0`` that blocks server-side until a job arrives — a 5s client
    read timeout turns every idle moment into a crash-and-reload loop. A longer
    connect timeout likewise keeps ``.kiq()`` from failing when the box is busy.
    """
    if not settings.redis_url or settings.redis_url == _MEMORY:
        return InMemoryBroker()
    broker: AsyncBroker = ListQueueBroker(
        settings.redis_url,
        queue_name="agent",
        socket_timeout=None,
        socket_connect_timeout=15,
    )
    if settings.taskiq_admin_url:
        broker.add_middlewares(
            TaskiqAdminMiddleware(
                url=settings.taskiq_admin_url,
                api_token=settings.taskiq_admin_token,
                taskiq_broker_name="agent",
            )
        )
    return broker


class AgentRunSpanMiddleware(TaskiqMiddleware):
    """One root ``agent.run`` span per task, from the worker's tracer provider.

    taskiq does not carry OTel context across ``.kiq()`` — a fresh root span per
    run is intended; LangChain's spans nest under it.
    """

    def __init__(self) -> None:
        super().__init__()
        self._spans: dict[str, Any] = {}

    def _start_span(self, message: TaskiqMessage) -> Any | None:
        provider = getattr(self.broker.state, "tracer_provider", None)
        if provider is None:
            return None
        tracer = provider.get_tracer("app.agent")
        return tracer.start_span(
            "agent.run",
            attributes={"taskiq.task": message.task_name, "taskiq.task_id": message.task_id},
        )

    def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        span = self._start_span(message)
        if span is not None:
            self._spans[message.task_id] = span
        return message

    def post_execute(self, message: TaskiqMessage, result: Any) -> None:
        span = self._spans.pop(message.task_id, None)
        if span is None:
            return
        if getattr(result, "is_err", False):
            span.set_attribute("error", True)
        span.end()

    def on_error(self, message: TaskiqMessage, result: Any, exception: BaseException) -> None:
        span = self._spans.pop(message.task_id, None)
        if span is None:
            return
        span.record_exception(exception)
        span.set_attribute("error", True)
        span.end()


broker = build_broker(get_settings())
broker.add_middlewares(AgentRunSpanMiddleware())


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def _on_startup(state: TaskiqState) -> None:
    # Imported here, not at module load: the gateway imports this module (via
    # `service.enqueue_run` -> `app.agent.tasks`) and must not pull in langchain.
    from app.agent.deps import build_worker_infra

    settings = get_settings()
    state.settings = settings
    state.tracer_provider = observability.setup_worker(settings)
    state.infra = await build_worker_infra(settings)


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def _on_shutdown(state: TaskiqState) -> None:
    infra = getattr(state, "infra", None)
    if infra is not None:
        await infra.aclose()
