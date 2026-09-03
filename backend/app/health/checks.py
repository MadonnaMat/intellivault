"""Deep health probes for every downstream dependency.

Each probe returns a :class:`ServiceStatus`; failures are captured, never
raised, so one dead dependency can't take down the whole ``/health`` response.
All probes run concurrently and share a per-probe timeout.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import perf_counter

import asyncpg
import httpx
from neo4j import AsyncDriver
from redis.asyncio import Redis

from app.config import Settings
from app.schemas import ServiceStatus

CHECK_TIMEOUT_SECONDS = 3.0
# Absolute ceiling on gather_health regardless of a probe stuck in a call
# that doesn't honour cancellation (e.g. a blocked getaddrinfo running in a
# worker thread). Stragglers past this are reported as failed and left to
# finish in the background rather than blocking /health.
OVERALL_TIMEOUT_SECONDS = CHECK_TIMEOUT_SECONDS + 3.0

# Holds references to abandoned straggler tasks so they aren't garbage
# collected mid-flight (which would log "Task was destroyed but it is pending").
_stragglers: set[asyncio.Task[ServiceStatus]] = set()


@dataclass(slots=True)
class HealthProbes:
    """Live handles the probes need, created once at application startup."""

    settings: Settings
    pg_pool: asyncpg.Pool
    neo4j_driver: AsyncDriver
    http_client: httpx.AsyncClient


ProbeResult = tuple[str, bool]  # (detail, degraded)


async def _measure(
    name: str,
    probe: Callable[[], Awaitable[ProbeResult]],
    *,
    critical: bool = True,
) -> ServiceStatus:
    start = perf_counter()
    try:
        detail, degraded = await asyncio.wait_for(probe(), timeout=CHECK_TIMEOUT_SECONDS)
        ok = True
    except TimeoutError:
        detail, degraded, ok = f"timed out after {CHECK_TIMEOUT_SECONDS:g}s", False, False
    except Exception as exc:  # noqa: BLE001 - report any failure, never propagate
        detail, degraded, ok = f"{type(exc).__name__}: {exc}", False, False
    return ServiceStatus(
        name=name,
        ok=ok,
        detail=detail,
        degraded=degraded,
        critical=critical,
        latency_ms=round((perf_counter() - start) * 1000, 1),
    )


async def _check_postgres(probes: HealthProbes) -> ProbeResult:
    value = await probes.pg_pool.fetchval("SELECT 1")
    if value != 1:
        raise RuntimeError(f"unexpected result: {value!r}")
    return "SELECT 1", False


async def _check_neo4j(probes: HealthProbes) -> ProbeResult:
    await probes.neo4j_driver.verify_connectivity()
    return "connectivity verified", False


async def _check_phoenix(probes: HealthProbes) -> ProbeResult:
    url = probes.settings.phoenix_collector_endpoint.rstrip("/") + "/healthz"
    response = await probes.http_client.get(url)
    response.raise_for_status()
    return f"GET /healthz -> {response.status_code}", False


async def _check_ollama(probes: HealthProbes) -> ProbeResult:
    settings = probes.settings
    url = settings.ollama_url.rstrip("/") + "/api/tags"
    response = await probes.http_client.get(url)
    response.raise_for_status()
    tags = {model["name"] for model in response.json().get("models", [])}

    def present(wanted: str) -> bool:
        return any(tag == wanted or tag.startswith(f"{wanted}:") for tag in tags)

    missing = [
        model
        for model in (settings.ollama_embed_model, settings.ollama_chat_model)
        if not present(model)
    ]
    if missing:
        return f"reachable; missing model(s): {', '.join(missing)}", True
    return "embed + chat models present", False


async def _check_redis(probes: HealthProbes) -> ProbeResult:
    # The agent-loop task queue. Non-critical: the gateway serves every read
    # without it — only POST /agent/runs (enqueue) needs Redis.
    client: Redis = Redis.from_url(probes.settings.redis_url)
    try:
        await client.ping()
    finally:
        await client.aclose()
    return "PING -> PONG", False


def _timed_out(name: str, critical: bool) -> ServiceStatus:
    return ServiceStatus(
        name=name,
        ok=False,
        detail=f"probe did not return within {OVERALL_TIMEOUT_SECONDS:g}s",
        degraded=False,
        critical=critical,
        latency_ms=round(OVERALL_TIMEOUT_SECONDS * 1000, 1),
    )


async def gather_health(probes: HealthProbes) -> list[ServiceStatus]:
    """Run every probe concurrently and return their statuses in a stable order.

    Bounded by OVERALL_TIMEOUT_SECONDS: a probe that hasn't returned by then is
    reported as failed and abandoned (left to complete in the background),
    so /health can't hang on an uncancellable call.
    """
    named_probes: list[tuple[str, Callable[[], Awaitable[ProbeResult]], bool]] = [
        ("postgres", lambda: _check_postgres(probes), True),
        ("neo4j", lambda: _check_neo4j(probes), True),
        ("phoenix", lambda: _check_phoenix(probes), False),
        ("ollama", lambda: _check_ollama(probes), True),
        ("redis", lambda: _check_redis(probes), False),
    ]
    tasks = {
        asyncio.ensure_future(_measure(name, probe, critical=critical)): (name, critical)
        for name, probe, critical in named_probes
    }

    done, pending = await asyncio.wait(tasks, timeout=OVERALL_TIMEOUT_SECONDS)

    results: dict[str, ServiceStatus] = {r.name: r for r in (task.result() for task in done)}
    for task in pending:
        name, critical = tasks[task]
        results[name] = _timed_out(name, critical)
        task.cancel()
        _stragglers.add(task)
        task.add_done_callback(_stragglers.discard)

    return [results[name] for name, _, _ in named_probes]
