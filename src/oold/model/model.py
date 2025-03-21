# generated by datamodel-codegen:
#   filename:  Foo.json
#   timestamp: 2025-03-18T03:44:32+00:00

from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from oold.model import LinkedBaseModel


class Bar2(LinkedBaseModel):
    id: Optional[str] = None
    type: Optional[List[str]] = ["Bar2"]
    prop1: Optional[str] = None


class Bar(Bar2):
    type: Optional[List[str]] = ["Bar"]
    prop2: Optional[str] = None


class Foo(LinkedBaseModel):
    id: Optional[str] = None
    type: Optional[List[str]] = ["Foo"]
    literal: Optional[str] = None
    b: Optional[Bar] = Field(None, json_schema_extra={"range": "Bar.json"})
    b2: Optional[List[Bar]] = Field(None, json_schema_extra={"range": "Bar.json"})
