"""OpenTelemetry tracing, exported to Arize-Phoenix.

Wiring here is best-effort: if Phoenix is unreachable at start-up the app still
comes up, it just won't emit traces. Instrumentation is explicit (no
``auto_instrument``):

* :func:`setup` — the FastAPI gateway: FastAPI + HTTPX spans.
* :func:`setup_worker` — the taskiq agent worker: LangChain (LLM / chain) + HTTPX
  spans. The worker also opens one root ``agent.run`` span per run
  (``app.agent.broker.AgentRunSpanMiddleware``).

Both share :func:`_register_tracer_provider`, which honours
``settings.tracing_enabled`` (tests set it false) and never raises.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import FastAPI

from app.config import Settings

logger = logging.getLogger(__name__)

TracerProvider = Any  # phoenix.otel.register's return type, kept import-free here
Span = Any  # opentelemetry.trace.Span, kept import-free here


def _register_tracer_provider(settings: Settings) -> TracerProvider | None:
    """Build a Phoenix-exporting tracer provider, or None. Never raises."""
    if not settings.tracing_enabled:
        logger.info("tracing_enabled=false, skipping OTel/Phoenix setup")
        return None
    try:
        from phoenix.otel import register
    except ImportError as exc:  # pragma: no cover - deps are declared, defensive only
        logger.warning("OTel/Phoenix packages missing, tracing disabled: %s", exc)
        return None
    try:
        return register(
            endpoint=settings.phoenix_collector_endpoint.rstrip("/") + "/v1/traces",
            project_name=settings.service_name,
            auto_instrument=False,
            set_global_tracer_provider=False,
            # BatchSpanProcessor exports on a background thread. The default
            # (SimpleSpanProcessor) exports synchronously on span end, which
            # blocks for the full connect timeout when Phoenix is unreachable —
            # the opposite of "best-effort".
            batch=True,
        )
    except Exception as exc:  # noqa: BLE001 - observability must not block start-up
        logger.warning("Phoenix/OTel register failed: %s", exc)
        return None


def setup(app: FastAPI, settings: Settings) -> None:
    """Register the tracer provider and instrument the gateway. Never raises."""
    provider = _register_tracer_provider(settings)
    if provider is None:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
        HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    except Exception as exc:  # noqa: BLE001 - observability must not block start-up
        logger.warning("Phoenix/OTel instrumentation disabled: %s", exc)
        return
    app.state.tracer_provider = provider


def get_provider(app: FastAPI) -> TracerProvider | None:
    """The gateway's tracer provider, or None (Phoenix down / tracing disabled)."""
    return getattr(app.state, "tracer_provider", None)


@contextmanager
def traced(
    provider: TracerProvider | None,
    tracer_name: str,
    span_name: str,
    *,
    kind: str,
    metadata: dict[str, Any] | None = None,
) -> Iterator[Span | None]:
    """Open one OpenInference-tagged span (or a no-op when tracing is off).

    ``kind`` is an OpenInference span kind ("AGENT", "TOOL", "CHAIN", ...) —
    Phoenix groups and renders spans by this. ``metadata`` becomes the span's
    ``metadata`` attribute (JSON), the place for "what was this called with,
    what did it do" details a plain span name can't carry.
    """
    if provider is None:
        yield None
        return
    from openinference.semconv.trace import SpanAttributes

    attributes: dict[str, Any] = {SpanAttributes.OPENINFERENCE_SPAN_KIND: kind}
    if metadata is not None:
        attributes[SpanAttributes.METADATA] = json.dumps(metadata, default=str)
    tracer = provider.get_tracer(tracer_name)
    with tracer.start_as_current_span(span_name, attributes=attributes) as span:
        yield span


def setup_worker(settings: Settings) -> TracerProvider | None:
    """Instrument the agent worker (LangChain + HTTPX). Never raises.

    Returns the provider so ``AgentRunSpanMiddleware`` can open a per-run span.
    """
    provider = _register_tracer_provider(settings)
    if provider is None:
        return None
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        LangChainInstrumentor().instrument(tracer_provider=provider)
        HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    except Exception as exc:  # noqa: BLE001 - observability must not block the worker
        logger.warning("worker instrumentation disabled: %s", exc)
    return provider
