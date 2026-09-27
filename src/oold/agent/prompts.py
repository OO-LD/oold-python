"""Building the prompt an enforcement condition implies.

Every difference between arms has to live here or in the request to the
provider, and nowhere else. If one arm also got a differently worded
instruction, a measured difference between arms would be partly a difference
in wording, which is the confound this whole design exists to remove.

So the instruction is one text with optional sections. The sections appear
exactly when the condition says they do, and the wording of the parts that
are shared is identical across arms, character for character.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from oold.agent.client import Message
from oold.agent.enforcement import Enforcement, OutputForm

__all__ = ["ExtractionRequest", "build_messages"]

_TASK = "Read the document and report every entity it describes, with the values stated for each."

_JSON_FORM = "Answer with JSON only. No explanation, no markdown fence, no commentary."

_PROSE_FORM = "Answer in plain prose. State each entity and the values given for it."

_CATALOGUE = "Choose the class of each entity from this list, using one of these exactly:"

_SCHEMA = "Each entity must conform to this schema:"

_GATE_HINT = "An entity whose class is not in the list will be discarded, so leave out anything you cannot place."


@dataclass(frozen=True)
class ExtractionRequest:
    """One document to read, and the schema material an arm may be shown."""

    document: str
    schema: dict[str, Any] | None = None
    """The target schema. Shown only when the condition says so, and sent to
    the provider only when a decode-time constraint is in force."""
    branches: dict[str, dict[str, Any]] | None = None
    """What each offered class narrows, for a union constraint. Supplied per
    request and not per condition, because it is corpus material like the
    schema beside it, and this package never learns what a corpus is."""
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

    if enforcement.catalogue:
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
