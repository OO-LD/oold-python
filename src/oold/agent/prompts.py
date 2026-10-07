"""Building the prompt an enforcement condition implies.

Every difference between arms has to live here or in the request to the
provider, and nowhere else. If one arm also got a differently worded
instruction, a measured difference between arms would be partly a difference
in wording, the confound this whole design exists to remove.

So the instruction is one text with optional sections. The sections appear
exactly when the condition says they do, and the wording of the parts that
are shared is identical across arms, character for character.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from oold.agent.client import Message
from oold.agent.enforcement import Enforcement, OutputForm

__all__ = [
    "ExtractionRequest",
    "build_messages",
    "build_property_messages",
    "build_selection_messages",
    "property_schema",
    "selection_schema",
]

_TASK = "Read the document and report every entity it describes, with the values stated for each."

_JSON_FORM = "Answer with JSON only. No explanation, no markdown fence, no commentary."

_PROSE_FORM = "Answer in plain prose. State each entity and the values given for it."

_CATALOGUE = "Choose the class of each entity from this list, using one of these exactly:"

_SCHEMA = "Each entity must conform to this schema:"

_SELECT_TASK = (
    "Read the document and say, for every entity it describes, which classes it could be. "
    "An entity is a thing the document describes, not a statement about one. "
    "A document that gives four properties of one thing describes one entity, not four, "
    "so list a thing once however many times the document mentions it, and do not list "
    "a property, a value or a field name as an entity of its own."
)
"""What to detect.

The second and third sentences were added after measurement: without them the
step returns roughly one entity per property mention. Over 120 two-entity
documents haiku planned 7.6 entities per document and gpt-5-nano 3.9, and a
traced case returned four ``LodgingBusiness`` for the four fields stated about
one hotel and three ``Rating`` for the three stated about one rating.

It says what an entity is and never how many there are. A count would be the
answer, and the step is being asked to find it.
"""

_SELECT_FORM = (
    "Answer with JSON only. For each entity give a short id, the classes it could "
    "belong to, most likely first, and the words that identify it in the document."
)
"""How to answer.

"The words that identify it" rather than the earlier "the words in the document
you read it from", which asked for a span and so invited one entry per span.
"""

_SELECT_SHORTLIST = (
    "List at most {k} classes per entity. Fewer is better when you are sure. "
    "A class you leave out cannot be chosen later."
)

_GATE_HINT = "An entity whose class is not in the list will be discarded, so leave out anything you cannot place."

_PROPERTY_TASK = (
    "Read the document and say, for each entity listed below, which of its own "
    "properties the document states a value for. A property is stated when the "
    "value itself appears in the text, in some spelling of it. Answer only "
    "from what the text in front of you says, never from what you know about "
    "the subject. A property the document makes likely, or that the entity "
    "would usually have, or that you could fill from memory, is not stated."
)
"""The rule the corpus actually applies, said out loud.

Ground truth here is a value whose spelling was found in the document. Six
models asked a looser question answered it six different ways, which is a
prompt that has not said what it wants rather than a disagreement between
models.

Memory is named because agreement showed it at work. Over six models in four
families, a property all six named was still rejected 29 per cent of the
time, and the clearest case is ``award`` on a film whose lead mentions no
award: six models agreeing is evidence about films, not about the document.
A model reading only the page cannot make that mistake.
"""

_PROPERTY_FORM = (
    "Answer with JSON only. Give one list of property names per entity, under that entity's id, "
    "using the names exactly as they are written here."
)

_PROPERTY_HONESTY = (
    "Both ways of being wrong cost something. A property you leave out will not be asked for again, "
    "so a value that is there is lost. A property you name will be asked for next, and if the "
    "document does not state it the answer has to be invented or left empty. Name the ones you "
    "could point at in the text."
)
"""Both costs, because naming one was the only one stated.

Measured on the Wikidata-schema.org corpus at gpt-5-nano: 21 properties
named that the document does not state against 6 missed, better than three
to one. A step told only that omission is irreversible has been told to
include when unsure, which is what it did.
"""

_PROPERTY_ENTITIES = "The entities, with the properties each one may carry:"


@dataclass(frozen=True)
class ExtractionRequest:
    """One document to read, and the schema material an arm may be shown."""

    document: str
    schema: dict[str, Any] | None = None
    property_evidence: bool = False
    """Whether the property step must quote the words it read each one from.

    Off, because it costs more than it buys: measured over six models, two
    invented *more* with a quotation required, gpt-oss-120b lost a third of
    its correct answers and claude-sonnet-5 over half. Raising the cost of
    answering is not the same as raising the cost of guessing.

    Kept as a condition because what a model writes there says what it
    thought it was reading, and that is worth being able to ask for."""
    property_text: Mapping[str, str] | None = None
    """What each property name means, for the step that chooses between them.

    Names alone do not say whether the gallery holding a painting is its
    ``contentLocation`` or its ``provider``. Measured over six models at
    n=100, the property step reaches a recall of 0.92 at a precision of 0.55:
    it finds the values and files them under the wrong slot, and no wording
    of the question fixes a vocabulary it was never shown.

    Read by that step alone, because it is the only one asked to tell two
    property names apart."""
    """The target schema. Shown only when the condition says so, and sent to
    the provider only when a decode-time constraint is in force."""
    branches: dict[str, dict[str, Any]] | None = None
    """What each offered class narrows, for a union constraint. Supplied per
    request and not per condition, because it is corpus material like the
    schema beside it, and this package never learns what a corpus is."""
    parents: dict[str, tuple[str, ...]] | None = None
    """Which classes each class inherits from.

    Supplied when the corpus has a hierarchy worth expressing. A union then
    states each property where it is declared instead of repeating every
    inherited one in every branch."""
    ranges: dict[str, tuple[str, ...]] | None = None
    """Which classes each node-valued property may point at.

    Supplied per request beside ``branches`` and ``parents``, and for the same
    reason: it is corpus material, and this package never learns what a corpus
    is. Keyed by property name alone. A reference slot is constrained by the
    classes the plan found on the page, not by the class that declares the
    property, so the declaring class adds nothing a second key could use."""
    instruction: str | None = None
    """Overrides the shared task sentence. For a study this stays unset, so
    every arm reads the same words."""


def build_messages(request: ExtractionRequest, enforcement: Enforcement) -> list[Message]:
    """The messages one arm sends for one document.

    The system message is assembled from sections, the user message is the
    document and nothing else. Keeping the document alone means the two are
    never confused for each other by a model that treats the last turn as the
    instruction.
    """
    sections: list[str] = [request.instruction or _TASK]

    sections.append(_PROSE_FORM if enforcement.output_form is OutputForm.PROSE else _JSON_FORM)

    if enforcement.catalogue and enforcement.catalogue_in_prompt:
        # Rendered entries when the condition supplies them, identifiers
        # otherwise. The identifier stays the answer either way, so a rendered
        # entry has to carry its own.
        entries = enforcement.catalogue_text or tuple(f"- {name}" for name in enforcement.catalogue)
        sections.append(f"{_CATALOGUE}\n" + "\n".join(entries))
        if enforcement.commit_gate:
            sections.append(_GATE_HINT)

    if enforcement.schema_in_prompt and request.schema is not None:
        sections.append(f"{_SCHEMA}\n{json.dumps(request.schema, indent=2)}")

    return [
        Message(role="system", content="\n\n".join(sections)),
        Message(role="user", content=request.document),
    ]


def selection_schema(catalogue: tuple[str, ...], k: int) -> dict[str, Any]:
    """The answer shape the select step asks for.

    ``candidates`` is ordered, most likely first, and capped at ``k``. The cap
    is in the schema and not only in the wording, because a shortlist that can
    grow to the whole catalogue does not narrow the choice and the second step would
    gain nothing.

    ``entities`` carries no ``maxItems``. How many entities a document describes
    is the question this step is asked, and capping it would answer it. The
    over-segmentation the cap would hide is addressed in the wording instead,
    at :data:`_SELECT_TASK`.
    """
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "EntityCandidates",
        "description": "Which classes each entity in the document could be.",
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "A short identifier for this entity, e.g. e1.",
                        },
                        "candidates": {
                            "type": "array",
                            "maxItems": k,
                            "items": {"type": "string", "enum": list(catalogue)},
                            "description": "Classes this entity could be, most likely first.",
                        },
                        "mention": {
                            "type": "string",
                            "description": (
                                "The words that identify this entity, not the properties it carries. "
                                "Give the same entity one line however often the document mentions it."
                            ),
                        },
                    },
                    "required": ["id", "candidates", "mention"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["entities"],
        "additionalProperties": False,
    }


def property_schema(offered: Mapping[str, Sequence[str]], evidence: bool = False) -> dict[str, Any]:
    """The answer shape the property step asks for.

    One array per entity, whose items enumerate **that entity's own** property
    names.

    Names alone. Asking for the words that state each property as well does
    not reduce invention and costs recall: measured over six models,
    deepseek-v3.2 and gpt-5-nano invented *more* with a quotation required,
    while gpt-oss-120b lost a third of its correct answers and
    claude-sonnet-5 over half. Raising the cost of answering is not the same
    as raising the cost of guessing. Pooling every entity's properties into one enumeration would let one
    entity be given another's property, which is the thing a per-entity
    enumeration is for, and it is the same argument that makes the fill step
    group by shortlist rather than pool the candidate classes.

    Refuses an entity with no properties. An empty ``enum`` is unsatisfiable
    rather than tight: the strict subsets reject it outright, and one that
    accepted it would leave a required array with no legal member.
    """
    if not offered:
        raise ValueError("the property step needs at least one entity with properties, or there is nothing to ask")
    empty = [key for key, names in offered.items() if not names]
    if empty:
        raise ValueError(f"no property is available for {', '.join(empty)}, so the enumeration would admit nothing")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "FillableProperties",
        "description": "Which properties of each entity the document gives a value for.",
        "type": "object",
        "properties": {
            "fillable": {
                "type": "object",
                "properties": {
                    key: {
                        "type": "array",
                        "maxItems": len(names),
                        "items": _property_item(list(names), evidence),
                        "description": f"The properties of {key} the document states a value for.",
                    }
                    for key, names in offered.items()
                },
                "required": list(offered),
                "additionalProperties": False,
            }
        },
        "required": ["fillable"],
        "additionalProperties": False,
    }


def _property_item(names: list[str], evidence: bool) -> dict[str, Any]:
    """One answered property, with or without the words that state it."""
    if not evidence:
        return {"type": "string", "enum": names}
    return {
        "type": "object",
        "properties": {
            "property": {"type": "string", "enum": names},
            "stated": {"type": "string", "description": "The words in the document that state it."},
        },
        "required": ["property", "stated"],
        "additionalProperties": False,
    }


def build_property_messages(
    request: ExtractionRequest,
    offered: Mapping[str, Sequence[str]],
    named: Mapping[str, str] | None = None,
) -> list[Message]:
    """The messages the property step sends.

    The document is the user message, as it is for every other step. The
    properties are listed in the system message as well as enumerated in the
    answer shape, because an arm that shows no schema still has to say what the
    names are before it can ask which of them the document fills.
    """
    described = request.property_text or {}
    if described:
        # One line per property, because a comment does not fit beside a name
        # and the step is choosing between them rather than scanning a list.
        lines: list[str] = []
        for key, names in offered.items():
            lines.append(f"{(named or {}).get(key) or key}:")
            lines += [f"  {name}: {described[name]}" if name in described else f"  {name}" for name in names]
        listed = "\n".join(lines)
    else:
        listed = "\n".join(f"{(named or {}).get(key) or key}: {', '.join(names)}" for key, names in offered.items())
    sections = [
        _PROPERTY_TASK,
        _PROPERTY_FORM,
        _PROPERTY_HONESTY,
        f"{_PROPERTY_ENTITIES}\n{listed}",
    ]
    return [
        Message(role="system", content="\n\n".join(sections)),
        Message(role="user", content=request.document),
    ]


def build_selection_messages(request: ExtractionRequest, enforcement: Enforcement, k: int) -> list[Message]:
    """The messages the select step sends.

    The catalogue section and the user message are identical to the ones the
    single-shot path sends, so the two orchestrations differ in what is asked
    and not in what is shown. Only the task sentence and the answer form
    change, because the question genuinely changed.
    """
    sections: list[str] = [_SELECT_TASK, _SELECT_FORM, _SELECT_SHORTLIST.format(k=k)]

    if enforcement.catalogue and enforcement.catalogue_in_prompt:
        entries = enforcement.catalogue_text or tuple(f"- {name}" for name in enforcement.catalogue)
        listed = "\n".join(entries)
        sections.append(f"{_CATALOGUE}\n{listed}")

    return [
        Message(role="system", content="\n\n".join(sections)),
        Message(role="user", content=request.document),
    ]
