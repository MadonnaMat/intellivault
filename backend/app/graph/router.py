"""Knowledge-graph routes: entities, relationships, visibility.

Thin HTTP shell over :mod:`app.graph.service`. Every route is tenant-scoped:
``owner_id`` is ``str(current_user.id)`` and the service bakes it into the
Cypher ``WHERE`` clause.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from neo4j import AsyncDriver

from app.auth.dependencies import current_user
from app.auth.schemas import SessionUser
from app.graph import service
from app.graph.db import get_driver
from app.graph.schemas import Entity, EntityInput, GraphView

router = APIRouter(prefix="/graph", tags=["graph"])

Driver = Annotated[AsyncDriver, Depends(get_driver)]
CurrentUser = Annotated[SessionUser, Depends(current_user)]


@router.get("")
async def get_graph(driver: Driver, user: CurrentUser) -> GraphView:
    """Every entity the caller may see: their own plus all public ones."""
    return await service.list_graph(driver, str(user.id))


@router.post("/entities", status_code=status.HTTP_201_CREATED)
async def create_entity(data: EntityInput, driver: Driver, user: CurrentUser) -> Entity:
    return await service.create_entity(driver, str(user.id), data)
