"""Per-property attribution: which declared property produced which RDF predicate.

This check has no counterpart in the reference harness. It exists because there are two ways a
``@context`` can fail a property, and looking only for the first misses the worse half.

**Dropped** - the term has no context definition at all, so the key vanishes on expansion. The
round-trip check catches this too, via a lost key.

**Suspicious** - the term maps through a prefix that was never defined. JSON-LD then reads
``schema:latitude`` as an absolute IRI whose scheme is literally ``schema``, so the key survives
expansion and the round-trip is lossless, while the predicate means nothing. Nothing about the
output looks wrong, which is what makes it dangerous.

Attribution is done by expanding one property at a time. Expanding the whole document tells you
which predicates came out but not which input key produced which, and that mapping is exactly
what is in question.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pyld import jsonld

from .loader import describe_jsonld_error

#: Keys in expanded output that mean "this term is a JSON-LD alias", not a predicate.
ALIAS_TARGETS = frozenset({"@id", "@type", "@graph", "@index", "@language", "@value", "@list", "@set"})

_ABSOLUTE_IRI = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.IGNORECASE)
_OTHER_SAFE_SCHEMES = ("urn:", "did:", "mailto:", "tag:", "_:")

#: A predicate no context term can produce, used to keep probe nodes alive during
#: single-property expansion. See :func:`classify_property`.
ANCHOR = "urn:oold:validation:anchor"

MAPPED = "mapped"
ALIAS = "alias"
DROPPED = "dropped"
SUSPICIOUS = "suspicious"


@dataclass
class PropertyOutcome:
    """What happened to one instance property when the document was expanded."""

    name: str
    status: str
    predicate: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "predicate": self.predicate,
            "detail": self.detail,
        }


@dataclass
class PredicateResult:
    """Attribution outcome for one instance."""

    ok: bool = True
    outcomes: list[PropertyOutcome] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    suspicious: dict[str, str] = field(default_factory=dict)
    aliased: dict[str, str] = field(default_factory=dict)
    mapped: dict[str, str] = field(default_factory=dict)
    undeclared: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self, include_documents: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "dropped": self.dropped,
            "suspicious": self.suspicious,
            "mapped_count": len(self.mapped),
            "aliased": self.aliased,
            "undeclared": self.undeclared,
            "errors": self.errors,
        }
        if include_documents:
            payload["outcomes"] = [o.to_dict() for o in self.outcomes]
            payload["mapped"] = self.mapped
        return payload


def is_grounded_predicate(iri: Any) -> bool:
    """True when a predicate IRI is absolute, and therefore actually means something."""
    if not isinstance(iri, str) or not iri:
        return False
    if iri.startswith("@"):
        return True
    if _ABSOLUTE_IRI.match(iri):
        return True
    return iri.startswith(_OTHER_SAFE_SCHEMES)


def classify_property(name: str, value: Any, context: Any, options: dict[str, Any]) -> PropertyOutcome:
    """Expand a single property in isolation to see which predicate it produces.

    The anchor is load-bearing. A node object carrying nothing but ``@id`` is free floating, and
    JSON-LD drops it on expansion, so a term aliased to ``@id`` would look dropped when it is in
    fact working correctly. Adding one predicate that cannot collide with a context term keeps
    the node alive, and it is filtered back out below.
    """
    try:
        expanded = jsonld.expand({"@context": context, name: value, ANCHOR: "anchor"}, options)
    except Exception as exc:
        return PropertyOutcome(name=name, status=DROPPED, detail=f"expansion failed: {describe_jsonld_error(exc)}")

    if not expanded:
        return PropertyOutcome(name=name, status=DROPPED, detail="no context term, so expansion produced no predicate")

    keys = set(expanded[0]) - {ANCHOR}
    if not keys:
        return PropertyOutcome(name=name, status=DROPPED, detail="no context term, so expansion produced no predicate")

    predicates = sorted(keys - ALIAS_TARGETS)
    if not predicates:
        alias = sorted(keys)[0]
        return PropertyOutcome(name=name, status=ALIAS, predicate=alias, detail=f"term is a JSON-LD alias for {alias}")

    predicate = predicates[0]
    if not is_grounded_predicate(predicate):
        prefix = predicate.split(":", 1)[0]
        return PropertyOutcome(
            name=name,
            status=SUSPICIOUS,
            predicate=predicate,
            detail=(
                f"expanded to {predicate!r}, which is not an absolute IRI; the {prefix!r} "
                "prefix is probably undefined in the context"
            ),
        )

    return PropertyOutcome(name=name, status=MAPPED, predicate=predicate)


def check_predicates(
    instance: dict[str, Any],
    context: Any,
    declared_properties: set[str] | None = None,
    options: dict[str, Any] | None = None,
) -> PredicateResult:
    """Classify every declared property of an instance.

    ``declared_properties`` limits the check to properties the schema actually declares.
    Generated instances routinely carry extra keys, because these schemas allow additional
    properties, and those keys have no context term by design. Counting them as dropped would
    bury the real findings in noise, so they are reported separately instead.
    """
    result = PredicateResult()
    options = options or {}

    payload_keys = [k for k in instance if not k.startswith("@") and k != "$schema"]
    if declared_properties is None:
        checked = payload_keys
    else:
        checked = [k for k in payload_keys if k in declared_properties]
        result.undeclared = sorted(k for k in payload_keys if k not in declared_properties)

    for name in checked:
        outcome = classify_property(name, instance[name], context, options)
        result.outcomes.append(outcome)
        if outcome.status == DROPPED:
            result.dropped.append(name)
        elif outcome.status == SUSPICIOUS:
            result.suspicious[name] = outcome.predicate or ""
        elif outcome.status == ALIAS:
            result.aliased[name] = outcome.predicate or ""
        else:
            result.mapped[name] = outcome.predicate or ""

    result.ok = not (result.dropped or result.suspicious or result.errors)
    return result
