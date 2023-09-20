# generated by datamodel-codegen:
#   filename:  Foo.json
#   timestamp: 2023-09-20T05:32:25+00:00

from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from ldc.model.static import LinkedBaseModel


class Bar(LinkedBaseModel):
    type: Optional[List[str]] = ["Bar"]
    prop1: Optional[str] = None


class Foo(LinkedBaseModel):
    type: Optional[List[str]] = ["Foo"]
    literal: Optional[str] = None
    b: Optional[Bar] = Field(None, range="Bar.json")
    b2: Optional[List[Bar]] = Field(None, range="Bar.json")
