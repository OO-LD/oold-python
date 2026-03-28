"""Test models for nested IRI serialization."""

from __future__ import annotations

from pydantic.v1 import Field

from oold.model.v1 import LinkedBaseModel


class Bar2(LinkedBaseModel):
    class Config:
        schema_extra = {"title": "Bar2"}

    id: str | None = None
    type: list[str] | None = ["Bar2"]
    prop1: str | None = None


class Bar(Bar2):
    class Config:
        schema_extra = {"title": "Bar"}

    type: list[str] | None = ["Bar"]
    prop2: str | None = None


class NestedItem(LinkedBaseModel):
    """A nested item with an IRI reference field."""

    class Config:
        schema_extra = {"title": "NestedItem"}

    id: str | None = None
    type: list[str] | None = ["NestedItem"]
    ref: Bar | None = Field(None, range="Bar.json")
    value: int | None = None


class Container(LinkedBaseModel):
    class Config:
        schema_extra = {"title": "Container"}

    id: str
    type: list[str] | None = ["Container"]
    items: list[NestedItem] | None = None
