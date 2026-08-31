"""Health endpoints: cheap liveness and deep dependency readiness."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from starlette.status import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE

from app.health.checks import HealthProbes, gather_health
from app.schemas import HealthResponse, HealthState, ServiceStatus

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def health_live() -> dict[str, str]:
    """Liveness probe — the process is up. Used by the container healthcheck."""
    return {"status": "ok"}


def _aggregate(services: list[ServiceStatus]) -> HealthState:
    if any(not service.ok and service.critical for service in services):
        return "down"
    if any(service.degraded or not service.ok for service in services):
        return "degraded"
    return "ok"


@router.get("/health", response_model=HealthResponse)
async def health(request: Request, response: Response) -> HealthResponse:
    """Deep readiness — probes Postgres, Neo4j, Phoenix and Ollama concurrently."""
    probes: HealthProbes = request.app.state.health_probes
    services = await gather_health(probes)
    status = _aggregate(services)
    response.status_code = HTTP_503_SERVICE_UNAVAILABLE if status == "down" else HTTP_200_OK
    return HealthResponse(status=status, services=services)
