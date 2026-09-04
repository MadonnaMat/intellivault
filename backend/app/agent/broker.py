"""The taskiq broker + worker lifecycle for the agent loop.

Run the worker as its own process:

    taskiq worker app.agent.broker:broker app.agent.tasks \
        --workers 1 --max-async-tasks $AGENT_WORKER_CONCURRENCY

This module must **not** import ``app.agent.tasks`` (the worker CLI names it
explicitly) — that keeps ``broker`` importable from the gateway's enqueue path
without pulling in langgraph.
"""

from __future__ import annotations

import json
from typing import Any

from taskiq import AsyncBroker, InMemoryBroker, TaskiqEvents, TaskiqMessage, TaskiqMiddleware
from taskiq.middlewares.taskiq_admin_middleware import TaskiqAdminMiddleware
from taskiq.state import TaskiqState
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

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

    The result backend is only actually consumed by tasks the caller waits on
    (``search_knowledge_graph_task``, via ``.wait_result()`` — see
    ``app.chat.graph_search``); ``run_agent``/``commit_agent_run`` stay
    fire-and-forget (progress lives in ``agent_runs``, not the task result).
    A short TTL keeps unread results from accumulating in Redis.
    """
    if not settings.redis_url or settings.redis_url == _MEMORY:
        return InMemoryBroker()
    broker: AsyncBroker = ListQueueBroker(
        settings.redis_url,
        queue_name="agent",
        socket_timeout=None,
        socket_connect_timeout=15,
    ).with_result_backend(RedisAsyncResultBackend(settings.redis_url, result_ex_time=300))
    if settings.taskiq_admin_url:
        broker.add_middlewares(
            TaskiqAdminMiddleware(
                url=settings.taskiq_admin_url,
                api_token=settings.taskiq_admin_token,
                taskiq_broker_name="agent",
            )
        )
    return broker


_SPAN_KIND_BY_TASK = {
    "run_agent": "AGENT",
    "commit_agent_run": "AGENT",
    "search_knowledge_graph_task": "CHAIN",
}

# Trace metadata/output is for "what was this called with, what did it
# return" at a glance, not a full data dump — cap it so a future task adding
# a large or sensitive argument (e.g. raw chat history) can't blow up span
# size unbounded.
_MAX_ATTR_LEN = 2000


def _capped_json(value: Any) -> str:
    text = json.dumps(value, default=str)
    if len(text) <= _MAX_ATTR_LEN:
        return text
    return text[:_MAX_ATTR_LEN] + f"... ({len(text)} chars total, truncated)"


class AgentRunSpanMiddleware(TaskiqMiddleware):
    """One root span per task, named for the task itself (not a blanket
    "agent.run") — so Phoenix's trace list tells run_agent, commit_agent_run,
    and search_knowledge_graph_task apart at a glance, from the worker's
    tracer provider.

    taskiq does not carry OTel context across ``.kiq()`` — a fresh root span per
    task is intended. The span is made the *current* context so LangChain's
    LLM/chain spans (and, for search_knowledge_graph_task, the LangGraph node
    spans) nest under it, and the provider is flushed when the task ends so its
    spans reach Phoenix even if the worker restarts right after.
    """

    def __init__(self) -> None:
        super().__init__()
        self._runs: dict[str, tuple[Any, Any]] = {}  # task_id -> (span, context token)

    def _provider(self) -> Any | None:
        return getattr(self.broker.state, "tracer_provider", None)

    def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        provider = self._provider()
        if provider is None:
            return message
        from openinference.semconv.trace import SpanAttributes
        from opentelemetry import context as otel_context
        from opentelemetry import trace as otel_trace

        attributes = {
            "taskiq.task": message.task_name,
            "taskiq.task_id": message.task_id,
            SpanAttributes.OPENINFERENCE_SPAN_KIND: _SPAN_KIND_BY_TASK.get(
                message.task_name, "CHAIN"
            ),
            SpanAttributes.METADATA: _capped_json({"args": message.args, "kwargs": message.kwargs}),
        }
        span = provider.get_tracer("app.agent").start_span(message.task_name, attributes=attributes)
        token = otel_context.attach(otel_trace.set_span_in_context(span))
        self._runs[message.task_id] = (span, token)
        return message

    def _end(self, task_id: str) -> None:
        entry = self._runs.pop(task_id, None)
        if entry is None:
            return
        span, token = entry
        span.end()
        from opentelemetry import context as otel_context

        otel_context.detach(token)
        provider = self._provider()
        if provider is not None:
            provider.force_flush()

    def post_execute(self, message: TaskiqMessage, result: Any) -> None:
        entry = self._runs.get(message.task_id)
        if entry is not None:
            span = entry[0]
            if getattr(result, "is_err", False):
                span.set_attribute("error", True)
            elif getattr(result, "return_value", None) is not None:
                # "what did this call return" — a task like
                # search_knowledge_graph_task returns its findings directly.
                from openinference.semconv.trace import SpanAttributes

                span.set_attribute(SpanAttributes.OUTPUT_VALUE, _capped_json(result.return_value))
        self._end(message.task_id)

    def on_error(self, message: TaskiqMessage, result: Any, exception: BaseException) -> None:
        entry = self._runs.get(message.task_id)
        if entry is not None:
            entry[0].record_exception(exception)
            entry[0].set_attribute("error", True)
        self._end(message.task_id)


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
    provider = getattr(state, "tracer_provider", None)
    if provider is not None:  # flush any spans still queued in the BatchSpanProcessor
        provider.shutdown()
