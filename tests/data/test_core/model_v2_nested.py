"""Test models for nested IRI serialization (pydantic v2)."""

from __future__ import annotations

from pydantic import ConfigDict, Field

from oold.model import LinkedBaseModel


class Bar2(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"title": "Bar2"})

    id: str | None = None
    type: list[str] | None = ["Bar2"]
    prop1: str | None = None


class Bar(Bar2):
    model_config = ConfigDict(json_schema_extra={"title": "Bar"})

    type: list[str] | None = ["Bar"]
    prop2: str | None = None


class NestedItem(LinkedBaseModel):
    """A nested item with an IRI reference field."""

    model_config = ConfigDict(json_schema_extra={"title": "NestedItem"})

    id: str | None = None
    type: list[str] | None = ["NestedItem"]
    ref: Bar | None = Field(None, json_schema_extra={"range": "Bar.json"})
    value: int | None = None


class Container(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"title": "Container"})

    id: str
    type: list[str] | None = ["Container"]
    items: list[NestedItem] | None = None
