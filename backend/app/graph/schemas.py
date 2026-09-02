"""Request/response models for the knowledge-graph routes.

``owner_id`` is always ``str(SessionUser.id)`` on the wire and a ``UUID`` here.
``attributes`` is a free-form flat-ish dict on the API; it is persisted as a
JSON string in Neo4j (properties can't nest) and is therefore not queryable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

Visibility = Literal["private", "public"]

Name = Annotated[str, Field(min_length=1, max_length=200)]
Kind = Annotated[str, Field(min_length=1, max_length=100)]


class EntityInput(BaseModel):
    """The caller-supplied fields when creating an entity."""

    name: Name
    kind: Kind
    visibility: Visibility = "private"
    attributes: dict[str, Any] = Field(default_factory=dict)


class Entity(BaseModel):
    """An entity node as returned to the caller."""

    id: UUID
    owner_id: UUID
    visibility: Visibility
    name: str
    kind: str
    attributes: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class RelationshipInput(BaseModel):
    """The caller-supplied fields when connecting two entities."""

    from_id: UUID
    to_id: UUID
    kind: Kind
    visibility: Visibility = "private"


class Relationship(BaseModel):
    """A ``RELATED_TO`` edge as returned to the caller."""

    id: UUID
    owner_id: UUID
    from_id: UUID
    to_id: UUID
    kind: str
    visibility: Visibility
    created_at: datetime
    updated_at: datetime


class GraphView(BaseModel):
    """Everything in the graph the caller may see."""

    entities: list[Entity]
    relationships: list[Relationship] = Field(default_factory=list)


class VisibilityChange(BaseModel):
    """Flip an entity's visibility, optionally cascading to its sub-graph."""

    visibility: Visibility
    # When true, also flip every caller-owned entity reachable from this one
    # over caller-owned relationships, and the caller-owned edges among them.
    cascade: bool = False


class VisibilityChangeResult(BaseModel):
    """The ids of every entity whose visibility actually changed."""

    affected_ids: list[UUID]
