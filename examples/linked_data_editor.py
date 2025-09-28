from enum import Enum
from typing import List, Optional

import panel as pn
from pydantic import ConfigDict, Field

from oold.model import LinkedBaseModel
from oold.ui.panel.demo import OoldDemoEditor


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
    type: Optional[str] = Field(
        "ex:Entity.json",
        json_schema_extra={"options": {"hidden": "true"}},
    )
    name: str

    def get_iri(self):
        return "ex:" + self.name


class Hobby(str, Enum):
    """Various hobbies as an enum."""

    SPORTS = "ex:sports"
    """Sports hobby, e.g. football, basketball, etc."""
    MUSIC = "ex:music"
    """Music hobby, e.g. playing instruments, singing, etc."""
    ART = "ex:art"
    """Art hobby, e.g. painting, drawing, etc."""


class Person(Entity):
    """A simple Person schema"""

    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity.json",  # import the context of the parent class
                {
                    # object property definition
                    "hobbies": {
                        "@id": "ex:hobbies",
                        "@type": "@id",
                    },
                    "knows": {
                        "@id": "schema:knows",
                        "@type": "@id",
                        "@container": "@set",
                    },
                },
            ],
            "iri": "Person.json",
            "defaultProperties": ["type", "name", "hobbies"],
        }
    )
    type: Optional[str] = "ex:Person.json"
    hobbies: Optional[List[Hobby]] = None
    """interests of the person, e.g. sports, music, art"""
    knows: Optional[List["Person"]] = Field(
        None,
        # object property pointing to another Person
        json_schema_extra={"range": "Person.json"},
    )


editor = OoldDemoEditor(Person)
pn.serve(editor.servable())
