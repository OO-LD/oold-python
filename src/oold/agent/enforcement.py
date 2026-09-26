"""Where structure is enforced, as data rather than as separate code paths.

Orchestration and enforcement are independent. The agent that walks a document
recursively and the agent that runs a five-step pipeline can both be given a
schema in the prompt, a decode-time constraint, a commit-time gate, all three,
or none. Entangling the two is what makes a comparison of typed against untyped
extraction impossible to interpret, because every measured difference has two
candidate causes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Literal

__all__ = [
    "ARMS",
    "DecodeConstraint",
    "Enforcement",
    "Orchestration",
    "OutputForm",
    "arm",
]


class Orchestration(str, Enum):
    """How the work is broken up, held constant while enforcement varies."""

    RECURSIVE = "recursive"
    """Depth first. Resolve each entity, recursing into its linked entities."""

    SEGMENTED = "segmented"
    """Plan the whole entity graph in one call, then fill it."""

    MULTI_STEP = "multi_step"
    """Detect, select properties, extract, construct, deduplicate."""


class DecodeConstraint(str, Enum):
    """What the model is prevented from emitting in the first place."""

    NONE = "none"
    """Free generation. Conformance is whatever the model volunteers."""

    JSON_SCHEMA = "json_schema"
    """Structured output against the schema, without a class enumeration."""

    JSON_SCHEMA_ENUM = "json_schema+enum"
    """Structured output with the class slot pinned to the catalogue."""


class OutputForm(str, Enum):
    """The shape the model is asked to answer in."""

    PROSE = "prose"
    JSON = "json"


@dataclass(frozen=True)
class Enforcement:
    """One point in the enforcement space.

    Every field is a separate question a reviewer can ask, and every field is
    set independently, so a result can be attributed to one of them.
    """

    schema_in_prompt: bool
    """Whether the target schema is shown to the model at all."""

    catalogue: tuple[str, ...] | None
    """Class paths offered for selection. ``None`` offers no catalogue, which
    is a different condition from offering an empty one. The length is the
    variable a catalogue-weight sweep moves."""

    decode_constraint: DecodeConstraint
    commit_gate: bool
    """Whether a produced class path is checked against the catalogue after
    generation, and the instance dropped when it cannot be resolved."""

    grounding: bool
    """Whether the schema keeps its ``@context`` and IRIs, or is flattened to
    a structured-output subset that carries the semantics in ``title`` and
    ``description`` instead."""

    output_form: OutputForm = OutputForm.JSON

    def __post_init__(self) -> None:
        if self.grounding and not self.schema_in_prompt:
            raise ValueError(
                "grounding needs a schema to ground; "
                "set schema_in_prompt when grounding is on"
            )
        if self.output_form is OutputForm.PROSE:
            if self.decode_constraint is not DecodeConstraint.NONE:
                raise ValueError(
                    "prose output cannot carry a decode-time constraint"
                )
            if self.commit_gate:
                raise ValueError("prose output has no class path to gate")

    @property
    def catalogue_size(self) -> int:
        """How many classes were offered. Zero when none were."""
        return 0 if self.catalogue is None else len(self.catalogue)

    def with_catalogue(self, paths: tuple[str, ...] | None) -> "Enforcement":
        """The same condition over a different catalogue.

        This is the one knob a catalogue-weight sweep moves, so it gets a
        method rather than being reconstructed by hand at each size.
        """
        return replace(self, catalogue=paths)

    def describe(self) -> dict[str, object]:
        """The condition, for the result record.

        Catalogue contents are not included; they are large and belong in a
        hash alongside the record. The size is here because it is the variable.
        """
        return {
            "schema_in_prompt": self.schema_in_prompt,
            "catalogue_size": self.catalogue_size,
            "catalogue_offered": self.catalogue is not None,
            "decode_constraint": self.decode_constraint.value,
            "commit_gate": self.commit_gate,
            "grounding": self.grounding,
            "output_form": self.output_form.value,
        }


ArmName = Literal["A0-prose", "A0-json", "A1", "A2", "A3"]

ARMS: dict[str, Enforcement] = {
    "A0-prose": Enforcement(
        schema_in_prompt=False,
        catalogue=None,
        decode_constraint=DecodeConstraint.NONE,
        commit_gate=False,
        grounding=False,
        output_form=OutputForm.PROSE,
    ),
    "A0-json": Enforcement(
        schema_in_prompt=False,
        catalogue=None,
        decode_constraint=DecodeConstraint.NONE,
        commit_gate=False,
        grounding=False,
        output_form=OutputForm.JSON,
    ),
    "A1": Enforcement(
        schema_in_prompt=True,
        catalogue=(),
        decode_constraint=DecodeConstraint.NONE,
        commit_gate=True,
        grounding=False,
    ),
    "A2": Enforcement(
        schema_in_prompt=True,
        catalogue=(),
        decode_constraint=DecodeConstraint.JSON_SCHEMA_ENUM,
        commit_gate=True,
        grounding=False,
    ),
    "A3": Enforcement(
        schema_in_prompt=True,
        catalogue=(),
        decode_constraint=DecodeConstraint.JSON_SCHEMA_ENUM,
        commit_gate=True,
        grounding=True,
    ),
}
"""The five arms, with an empty catalogue that a run fills in.

A0 is two arms rather than one. ``A0-json`` is the headline comparison, because
its output reduces to triples by the same path as every other arm and needs no
judge. ``A0-prose`` is reported beside it with the parse loss of its extractor
stated, so the objection that JSON is already a form of structure has an answer
in the results rather than in the discussion.
"""


def arm(name: str, catalogue: tuple[str, ...] | None = None) -> Enforcement:
    """One of the five arms, over a given catalogue."""
    if name not in ARMS:
        raise KeyError(f"unknown arm {name!r}, expected one of {sorted(ARMS)}")
    base = ARMS[name]
    if catalogue is None:
        return base
    if base.catalogue is None:
        raise ValueError(f"arm {name} offers no catalogue")
    return base.with_catalogue(catalogue)
