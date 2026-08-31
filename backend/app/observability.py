"""OpenTelemetry tracing, exported to Arize-Phoenix.

Wiring here is best-effort: if Phoenix is unreachable at start-up the app still
comes up, it just won't emit traces. Instrumentation is explicit (no
``auto_instrument``) so only the FastAPI and HTTPX integrations are enabled.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from app.config import Settings

logger = logging.getLogger(__name__)


def setup(app: FastAPI, settings: Settings) -> None:
    """Register the tracer provider and instrument the app. Never raises."""
    if not settings.tracing_enabled:
        logger.info("tracing_enabled=false, skipping OTel/Phoenix setup")
        return

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from phoenix.otel import register
    except ImportError as exc:  # pragma: no cover - deps are declared, defensive only
        logger.warning("OTel/Phoenix packages missing, tracing disabled: %s", exc)
        return

    try:
        tracer_provider = register(
            endpoint=settings.phoenix_collector_endpoint.rstrip("/") + "/v1/traces",
            project_name=settings.service_name,
            auto_instrument=False,
            set_global_tracer_provider=False,
            # BatchSpanProcessor exports on a background thread. The default
            # (SimpleSpanProcessor) exports synchronously on span end, which
            # blocks every request for the full connect timeout when Phoenix
            # is unreachable — the opposite of "best-effort".
            batch=True,
        )
        FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider)
        HTTPXClientInstrumentor().instrument(tracer_provider=tracer_provider)
    except Exception as exc:  # noqa: BLE001 - observability must not block start-up
        logger.warning("Phoenix/OTel instrumentation disabled: %s", exc)
