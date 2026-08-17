"""Projecting an instance to RDF and reconstructing it.

Two different comparisons are needed, because two different questions are being asked.

:func:`lost_keys` answers "did any property fall out?" It compares keys only and ignores leaf
values, which is right for a *generated* instance: a property with no (or a broken) ``@context``
term produces no triples and its key disappears, while value coercion - a reference string
resolving to an absolute IRI - keeps the key and so must not be reported.

:func:`canonical` answers "is the reconstruction equal to the original?" It is used for
*committed* instances, where the exact values matter too.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pyld import jsonld

from .frame import embedded_properties, instance_rdf_types, schema_to_frame
from .loader import DocumentLoader, describe_jsonld_error

#: Keys that are metadata rather than data, and are excluded from both comparisons.
_METADATA_KEYS = frozenset({"@context", "$schema"})


def _sort_key(value: Any) -> str:
    # Compact separators so ordering matches JSON.stringify in the reference implementation.
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str)


def canonical(value: Any) -> Any:
    """A comparable normal form: metadata dropped, arrays sorted, cardinality flattened.

    Sorting array members is correct because RDF sets are unordered. Treating a single value and
    a one-element array alike is JSON-LD semantics rather than laxness: ``"x"`` and ``["x"]``
    expand identically, and compaction picks the scalar or array form depending on whether the
    term declares ``@container: @set``, so cardinality may legitimately differ between an
    instance and its round-trip without any loss. The ``@container`` requirement is enforced
    separately and statically by the pattern lint.
    """
    if isinstance(value, list):
        return sorted((canonical(item) for item in value), key=_sort_key)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key in sorted(value):
            if key in _METADATA_KEYS:
                continue
            if key == "@id":
                # Blank-node identifiers are arbitrary labels, not stable identity: a blank node
                # acquires a `_:bN` label on the way back from RDF that it did not carry before.
                # Drop @id when every value is such a label, so the node compares equal.
                values = value[key] if isinstance(value[key], list) else [value[key]]
                if all(isinstance(v, str) and v.startswith("_:") for v in values):
                    continue
            member = value[key]
            out[key] = canonical(member if isinstance(member, list) else [member])
        return out
    return value


def json_equal(left: Any, right: Any) -> bool:
    """Structural equality with JSON semantics, notably keeping booleans distinct from 1/0.

    Python would otherwise treat ``True == 1`` as equal, which JSON and JSON-LD do not. Numbers
    are compared by value so ``1`` and ``1.0`` match, which is what the reference implementation
    does implicitly by having a single number type.
    """
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(json_equal(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return False
        return all(json_equal(a, b) for a, b in zip(left, right, strict=True))
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    return type(left) is type(right) and left == right


def is_noop(value: Any) -> bool:
    """True for a JSON-LD no-op value: ``null``, ``[]``, or nested arrays of those.

    Such a value produces no triples, so its key legitimately disappears on the way back and
    must not be reported as lost.
    """
    if value is None:
        return True
    return isinstance(value, list) and all(is_noop(item) for item in value)


def lost_keys(before: Any, after: Any, path: str = "", lost: list[str] | None = None) -> list[str]:
    """Property keys present in ``before`` but missing from ``after``, compared recursively."""
    if lost is None:
        lost = []
    if is_noop(before):
        return lost

    if isinstance(before, list):
        if isinstance(after, list):
            candidates = after
        elif after is None:
            candidates = []
        else:
            candidates = [after]
        for element in before:
            if isinstance(element, (dict, list)) and not any(
                not lost_keys(element, candidate, path, []) for candidate in candidates
            ):
                lost.append(f"{path}[]")
        return lost

    if isinstance(before, dict):
        if isinstance(after, dict):
            target = after
        elif isinstance(after, list):
            target = next((x for x in after if isinstance(x, dict)), {})
        else:
            target = {}
        for key in before:
            if key in _METADATA_KEYS or is_noop(before[key]):
                continue
            here = f"{path}.{key}" if path else key
            if key not in target:
                lost.append(here)
            else:
                lost_keys(before[key], target[key], here, lost)
    return lost


@dataclass
class RoundtripResult:
    """One instance through RDF and back."""

    ok: bool = True
    lost: list[str] = field(default_factory=list)
    restored: Any = None
    triples: int = 0
    method: str = ""
    error: str | None = None
    nquads: str = ""

    def to_dict(self, include_documents: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "lost": self.lost,
            "triples": self.triples,
            "method": self.method,
        }
        if self.error:
            payload["error"] = self.error
        if include_documents:
            payload["restored"] = self.restored
            payload["nquads"] = self.nquads
        return payload


def roundtrip(
    schema: dict[str, Any],
    sample: Any,
    context_ref: Any,
    loader: DocumentLoader,
    base: str | None = None,
) -> RoundtripResult:
    """Round-trip an instance as a compliant export and report what was dropped.

    The declared ``rdf:type``(s) are materialised as ``@type`` unless the instance already
    carries one, the document is projected to RDF and back, and it is reconstructed by framing
    when the schema embeds objects or by plain compaction when it does not.
    """
    result = RoundtripResult()

    # A scalar instance (a DataType leaf schema whose body is a bare string or boolean) has no
    # properties to lose and cannot carry a @context; there is nothing to round-trip.
    if not isinstance(sample, dict):
        result.restored = sample
        return result

    rdf_base = base if base is not None else context_ref
    document: dict[str, Any] = {"@context": context_ref}
    document.update({k: v for k, v in sample.items() if k != "@context"})

    types = instance_rdf_types(schema)
    if types and "type" not in sample and "@type" not in sample:
        document["@type"] = list(types)

    try:
        nquads = jsonld.to_rdf(document, loader.options(base=rdf_base, format="application/n-quads"))
        result.nquads = nquads
        result.triples = sum(1 for line in nquads.split("\n") if line.strip())

        back = jsonld.from_rdf(nquads, {"format": "application/n-quads", "useNativeTypes": True})

        if embedded_properties(schema):
            result.method = "framed"
            result.restored = jsonld.frame(
                back,
                schema_to_frame(schema, context_ref),
                loader.options(base=rdf_base, omitDefault=True),
            )
        else:
            result.method = "compacted"
            result.restored = jsonld.compact(back, context_ref, loader.options(base=rdf_base))
    except Exception as exc:
        result.ok = False
        result.error = describe_jsonld_error(exc)
        return result

    result.lost = lost_keys(sample, result.restored)
    result.ok = not result.lost
    return result


def canonical_equal(before: Any, after: Any) -> bool:
    """Whether an instance and its reconstruction are equal in canonical form."""
    return json_equal(canonical(before), canonical(after))
