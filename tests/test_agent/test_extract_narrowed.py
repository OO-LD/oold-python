"""extract_narrowed: the door for a caller holding its own oracle.

A step harness scoring extraction alone already knows an entity's true class
and, where it has one, the true set of fillable properties, the same pair
`_multi_step` derives for itself one step earlier. `extract()` sends every
class and every property the condition's catalogue carries regardless, so a
class the plan already settled is still something the model can get wrong,
and a property the plan never named is still something it can invent a value
for. These pin both, and pin neither where the caller does not ask.
"""

from __future__ import annotations

import json

from oold.agent.client import ChatResponse, TokenUsage
from oold.agent.enforcement import arm
from oold.agent.extraction import ExtractionAgent, PlannedEntity
from oold.agent.prompts import ExtractionRequest
from oold.agent.provider import profile_for

CATALOGUE = ("Person", "Organization", "LocalBusiness", "Book")

BRANCHES = {
    "Person": {"jobTitle": {"type": "string"}, "worksFor": {"type": "object"}},
    "Organization": {"legalName": {"type": "string"}, "founder": {"type": "object"}},
    "LocalBusiness": {"openingHours": {"type": "string"}},
    "Book": {"isbn": {"type": "string"}},
}

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Entities",
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "name": {"type": "string"},
                    "jobTitle": {"type": "string"},
                    "worksFor": {"type": "object"},
                    "legalName": {"type": "string"},
                    "founder": {"type": "object"},
                    "openingHours": {"type": "string"},
                    "isbn": {"type": "string"},
                },
                "required": ["type"],
            },
        }
    },
    "required": ["entities"],
}

DOCUMENT = "Ada works for Acme."


class RecordingClient:
    """Answers once, with a fixed payload, and keeps the request it was sent."""

    model = "recorder"

    def __init__(self, payload):
        self.payload = payload
        self.formats: list = []

    def invoke(self, messages, *, response_format=None, strict=False) -> ChatResponse:
        self.formats.append(response_format)
        return ChatResponse(
            text=json.dumps(self.payload), parsed=None, usage=TokenUsage(input_tokens=10, output_tokens=5)
        )


def agent(client) -> ExtractionAgent:
    return ExtractionAgent(client, arm("schema-dump-catalog-enforced", CATALOGUE), profile_for("openai"))


def request() -> ExtractionRequest:
    return ExtractionRequest(document=DOCUMENT, schema=SCHEMA, branches=BRANCHES)


def branch_names(response_format) -> set[str]:
    return {branch["properties"]["type"]["const"] for branch in response_format["properties"]["entities"]["items"]["anyOf"]}


def branch_properties(response_format, name: str) -> set[str]:
    branches = response_format["properties"]["entities"]["items"]["anyOf"]
    branch = next(b for b in branches if b["properties"]["type"]["const"] == name)
    return set(branch["properties"])


class TestExtractNarrowed:
    def test_the_union_is_narrowed_to_the_given_class(self):
        client = RecordingClient({"entities": [{"id": "e1", "type": "Person", "name": "Ada"}]})
        result = agent(client).extract_narrowed(
            request(), plan=(PlannedEntity(key="e1", classes=("Person",), mention="Ada"),),
            filling=("e1",), classes=("Person",),
        )
        assert result.payload is not None
        assert branch_names(client.formats[0]) == {"Person"}

    def test_plain_extract_sends_the_whole_catalogue_unnarrowed(self):
        """The negative control: extract() itself is unchanged."""
        client = RecordingClient({"entities": [{"id": "e1", "type": "Person", "name": "Ada"}]})
        agent(client).extract(
            request(), plan=(PlannedEntity(key="e1", classes=("Person",), mention="Ada"),), filling=("e1",)
        )
        assert branch_names(client.formats[0]) == set(CATALOGUE)

    def test_properties_none_keeps_every_property_the_narrowed_class_admits(self):
        client = RecordingClient({"entities": [{"id": "e1", "type": "Person", "name": "Ada", "jobTitle": "Engineer"}]})
        agent(client).extract_narrowed(
            request(), plan=(PlannedEntity(key="e1", classes=("Person",), mention="Ada"),),
            filling=("e1",), classes=("Person",),
        )
        assert branch_properties(client.formats[0], "Person") >= {"jobTitle", "worksFor", "name"}

    def test_properties_given_trims_to_exactly_those(self):
        client = RecordingClient({"entities": [{"id": "e1", "type": "Person", "name": "Ada"}]})
        agent(client).extract_narrowed(
            request(),
            plan=(PlannedEntity(key="e1", classes=("Person",), mention="Ada"),),
            filling=("e1",),
            classes=("Person",),
            properties=("name",),
        )
        kept = branch_properties(client.formats[0], "Person")
        assert "name" in kept
        assert "jobTitle" not in kept
        assert "worksFor" not in kept

    def test_the_id_slot_is_still_pinned_to_filling(self):
        """Narrowing the class must not cost what `extract()` already pins."""
        client = RecordingClient({"entities": [{"id": "e1", "type": "Person", "name": "Ada"}]})
        agent(client).extract_narrowed(
            request(), plan=(PlannedEntity(key="e1", classes=("Person",), mention="Ada"),),
            filling=("e1",), classes=("Person",),
        )
        branches = client.formats[0]["properties"]["entities"]["items"]["anyOf"]
        assert all(branch["properties"]["id"]["enum"] == ["e1"] for branch in branches)

    def test_two_entities_of_different_classes_both_narrow(self):
        client = RecordingClient({
            "entities": [
                {"id": "e1", "type": "Person", "name": "Ada"},
                {"id": "e2", "type": "Organization", "name": "Acme"},
            ]
        })
        plan = (
            PlannedEntity(key="e1", classes=("Person",), mention="Ada"),
            PlannedEntity(key="e2", classes=("Organization",), mention="Acme"),
        )
        agent(client).extract_narrowed(request(), plan=plan, filling=("e1", "e2"), classes=("Person", "Organization"))
        assert branch_names(client.formats[0]) == {"Person", "Organization"}
