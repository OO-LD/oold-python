"""Resolve Wikidata entities as typed objects over a public SPARQL endpoint.

Shows the binding against a backend nobody controls: the classes below declare
only a JSON-LD context and which properties are links, and
``Person["Item:Q80"]`` turns an IRI into a ``Person`` whose ``father`` is another
``Person``, fetched on first access.

Run it:

    python examples/wiki_data.py

Two details are specific to Wikidata:

* the class IRI is the **expanded** entity IRI, because that is what arrives in
  ``@type``; the registry matches type IRIs literally, without prefix expansion;
* the resolver rewrites ``wdt:P31`` (instance of) into ``@type``, so the context
  aliases ``type`` to ``@type`` rather than mapping it to P31.
"""

from pydantic import ConfigDict

from oold.backend.interface import SetResolverParam, set_resolver
from oold.backend.sparql import WikiDataSparqlResolver

# The descriptor binding (pydantic v2). Imported directly rather than as
# oold.model.LinkedBaseModel, because Link[T] is part of this binding and the
# swap is still behind OOLD_DESCRIPTOR_BINDING.
from oold.model._descriptor import (
    AutoLinkedModel,
    Link,
    LinkNotResolved,
    OoldField,
)

WD_ENTITY = "http://www.wikidata.org/entity/"
ENTITY_SCHEMA = "https://oo-ld.org/examples/wikidata/Entity"


class WikiDataEntity(AutoLinkedModel):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": {
                # aliases
                "id": "@id",
                "type": "@type",
                # prefixes
                "p": "http://www.wikidata.org/prop/",
                "wdt": "http://www.wikidata.org/prop/direct/",
                "Item": WD_ENTITY,
                "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
                # rdfs:label is language-tagged and multi-valued; scoping the
                # term to one language makes it compact to a plain string.
                # wdt:P373 (Commons category) would read more directly but is
                # sparse - most entities do not carry one.
                "name": {"@id": "rdfs:label", "@language": "en"},
            },
            "iri": ENTITY_SCHEMA,  # the IRI of the schema
        }
    )
    id: str
    type: str | None = None
    name: str | None = None

    def get_iri(self):
        return self.id


class Person(WikiDataEntity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                ENTITY_SCHEMA,  # import the context of the parent class
                {
                    # object property pointing to another Person
                    "father": {
                        "@id": "wdt:P22",
                        "@type": "@id",
                    },
                },
            ],
            # The class IRI has to be the expanded form: it is compared with the
            # @type of the incoming document, and Q5 is "human".
            "iri": WD_ENTITY + "Q5",
        }
    )
    type: str | None = "Item:Q5"
    # Link[T] rather than "Person | None": the annotation says what *reading*
    # the link yields, so a chain can be written plainly and guarded once.
    # Ancestry does run out - that is what the try/except in main() is for.
    father: Link["Person"] = OoldField(range=WD_ENTITY + "Q5")


Person.model_rebuild()

# Wikidata attributes requests by user agent and throttles the ones it cannot
# place - the SPARQLWrapper default is answered with "429 Aggressively
# rate-limiting to 1 req / min". The resolver sends a descriptive one by default.
set_resolver(
    SetResolverParam(
        iri="Item",
        resolver=WikiDataSparqlResolver(endpoint="https://query.wikidata.org/sparql"),
    )
)


def main() -> None:
    person = Person["Item:Q80"]  # Tim Berners-Lee
    assert person is not None, "Q80 not resolved - the endpoint may be unavailable"
    print("resolved:", person.id)
    print("name:    ", person.name)
    print("type:    ", person.type)

    # the link is an IRI in the payload and a Person once read
    print("\nfather is fetched on access, not on construction")
    print("  stored IRI:", person.get_iri_ref("father"))
    father = person.father
    assert isinstance(father, Person), type(father)
    print("  resolved:  ", father.id, "-", father.name)

    print("\nplain chaining - no guard, no narrowing, no cast")
    ggf = person.father.father.father
    print("  great-grandfather:", ggf.name)

    print("\nthe same walk, until the data runs out")
    ancestor, generations = person, 0
    try:
        while True:
            ancestor = ancestor.father
            generations += 1
            print(f"  {generations} generation(s) back:", ancestor.name)
    except LinkNotResolved:
        # Ancestry runs out. Declaring the link mandatory is what turns that
        # into one exception at the end rather than a guard at every hop.
        print(f"  no father recorded for {ancestor.name} - walked {generations} generation(s)")

    print("\nquery: the same DSL, translated to SPARQL by the resolver")
    found = Person[Person.name == "Tim Berners-Lee"]
    print("  Person[Person.name == 'Tim Berners-Lee'] ->", [p.id for p in found or []])

    print("\nserialisation writes the link back as an IRI")
    dumped = person.to_json()
    print("  father ->", dumped["father"])

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
