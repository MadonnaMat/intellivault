"""The get_driver dependency returns the driver stashed on app.state."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from fastapi import Request

from app.graph.db import get_driver


def test_get_driver_returns_app_state_driver() -> None:
    sentinel = object()
    request = cast(
        Request, SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(neo4j_driver=sentinel)))
    )
    assert get_driver(request) is sentinel
