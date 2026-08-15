from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from oold.model import LinkedBaseModel  # based on pydantic v2


class Entity(LinkedBaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": {
                # aliases
                "id": "@id",
                "type": "@type",
                # prefixes
                "schema": "https://schema.org/",
                "ex": "https://example.com/",
                # literal property
                "name": "schema:name",
            },
            "iri": "Entity.json",  # the IRI of the schema
        }
    )
    type: Optional[str] = "ex:Entity"
    name: str

    def get_iri(self):
        return "ex:" + self.name


class LengthUnit(str, Enum):
    m = "qudt:Meter"
    mm = "qudt:Millimeter"
    cm = "qudt:Centimeter"


class QuantityValue(BaseModel):
    value: float
    unit: Any


class Length(QuantityValue):
    unit: LengthUnit = LengthUnit.m


class WidthChange(Length):
    unit: LengthUnit = LengthUnit.mm
    value: float = 1.0


class TensileTestData(LinkedBaseModel):
    Breitenaenderung: Optional[WidthChange]


class Details(LinkedBaseModel):
    Bemerkung: Optional[str]


class TesileTest(LinkedBaseModel):
    details: Optional[Details]
