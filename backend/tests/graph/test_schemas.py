"""Validation rules on the graph request/response models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.graph.schemas import EntityInput


def test_visibility_rejects_junk() -> None:
    with pytest.raises(ValidationError):
        EntityInput(name="x", kind="y", visibility="secret")


def test_visibility_defaults_to_private() -> None:
    assert EntityInput(name="x", kind="y").visibility == "private"


def test_attributes_default_is_an_empty_dict() -> None:
    assert EntityInput(name="x", kind="y").attributes == {}


def test_name_and_kind_are_required_non_empty() -> None:
    with pytest.raises(ValidationError):
        EntityInput(name="", kind="y")
