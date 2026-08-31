"""Pydantic response models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

HealthState = Literal["ok", "degraded", "down"]


class ServiceStatus(BaseModel):
    """Result of probing a single downstream dependency."""

    name: str
    ok: bool
    detail: str
    latency_ms: float
    # Reachable but not fully ready (e.g. a required model not pulled).
    degraded: bool = False


class HealthResponse(BaseModel):
    """Aggregate health across every downstream dependency."""

    status: HealthState
    services: list[ServiceStatus]
