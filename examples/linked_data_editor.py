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


class Person(Entity):
    """A simple Person schema"""

    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity.json",  # import the context of the parent class
                {
                    # object property definition
                    "knows": {
                        "@id": "schema:knows",
                        "@type": "@id",
                        "@container": "@set",
                    }
                },
            ],
            "iri": "Person.json",
            "defaultProperties": ["type", "name"],
        }
    )
    type: Optional[str] = "ex:Person.json"
    knows: Optional[List["Person"]] = Field(
        None,
        # object property pointing to another Person
        json_schema_extra={"range": "Person.json"},
    )


editor = OoldDemoEditor(Person)
pn.serve(editor.servable())
