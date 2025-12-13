from typing import List, Optional

from pydantic import ConfigDict, Field

from oold.backend.interface import SetResolverParam, set_resolver
from oold.backend.sparql import WikiDataSparqlResolver

# based on pydantic v2
from oold.model import LinkedBaseModel  # noqa


class MultiLanguageString(LinkedBaseModel):
    text: str
    lang: str


class WikiDataEntity(LinkedBaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": {
                # aliases
                "id": "@id",
                # prefixes
                "p": "http://www.wikidata.org/prop/",
                "wdt": "http://www.wikidata.org/prop/direct/",
                "Item": "http://www.wikidata.org/entity/",
                "type": "wdt:P31",
                "name": {
                    "@id": "wdt:P373",
                    "@type": "http://www.w3.org/2001/XMLSchema#string",
                },
                # "label": {
                #     "@id": "http://www.w3.org/2000/01/rdf-schema#label",
                #     "@container": "@set",
                #     "@context": {
                #         "text": "@value",
                #         "lang": "@language",
                #     }
                # },
            },
            "iri": "Entity.json",  # the IRI of the schema
        }
    )
    id: str
    type: Optional[str]
    # label: Optional[List[MultiLanguageString]] = None
    name: Optional[str] = None

    @classmethod
    def get_class_iri(cls):
        # return default value of field 'type' if not set
        if (
            cls.model_fields.get("type")
            and cls.model_fields["type"].default is not None
        ):
            return cls.model_fields["type"].default

    def get_iri(self):
        return "ex:" + self.name


class Person(WikiDataEntity):  # noqa
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                "Entity.json",  # import the context of the parent class
                {
                    # object property definition
                    "father": {
                        "@id": "wdt:P22",
                        "@type": "@id",
                    },
                    "knows": {
                        "@id": "schema:knows",
                        "@type": "@id",
                        "@container": "@set",
                    },
                },
            ],
            "iri": "Q5",
        }
    )
    type: Optional[str] = "wd:Q5"  # Q5 is the Wikidata item for human
    father: Optional["Person"] = Field(
        None,
        json_schema_extra={"range": "Person.json"},
    )
    knows: Optional[List["Person"]] = Field(
        None,
        # object property pointing to another Person
        json_schema_extra={"range": "Person.json"},
    )


# create a resolver to resolve IRIs to objects


r = WikiDataSparqlResolver(endpoint="https://query.wikidata.org/sparql")
set_resolver(SetResolverParam(iri="Item", resolver=r))

# Example usage:
p = Person["Item:Q80"]  # Douglas Adams
print(p.model_dump_json(indent=2))
print(p)
print(p.father)
print(p.father.father)
