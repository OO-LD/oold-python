from typing import List, Optional

from pydantic import Field
from pydantic.v1 import BaseModel

from oold.model.v1 import LinkedBaseModel


class Bar2(BaseModel):
    class Config:
        schema_extra = {"title": "Bar2"}

    id: Optional[str] = None
    type: Optional[List[str]] = ["Bar2"]
    prop1: Optional[str] = None


class Bar(Bar2):
    class Config:
        schema_extra = {"title": "Bar"}

    type: Optional[List[str]] = ["Bar"]
    prop2: Optional[str] = None


class Foo(BaseModel):
    class Config:
        schema_extra = {"title": "Foo"}

    id: str
    type: Optional[List[str]] = ["Foo"]
    literal: Optional[str] = None
    b: Optional[Bar] = Field(
        default_factory=lambda: Bar.parse_obj("ex:b"), range="Bar.json"
    )
    b_default: Optional[Bar] = Field(
        default_factory=lambda: Bar.parse_obj("ex:b"),
        range="Bar.json",
        x_oold_required_iri=True,
    )
    b2: Optional[List[Bar]] = Field(None, range="Bar.json")


f = Foo(id="ex:f")
