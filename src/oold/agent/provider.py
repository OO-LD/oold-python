"""Per-provider schema preparation, with a record of what it cost.

Providers accept different subsets of JSON Schema, so the same OO-LD schema
reaches each of them differently. That makes the transform part of the
treatment, not a utility: if one provider is handed a schema that lost its
constraints and another is not, a measured difference between them is partly a
difference between transforms. So the profile is declared in configuration
rather than sniffed from a model name, the prepared schema is hashed into the
result, and what the transform removed is reported as a number.

The combinator flattening follows the approach taken by LiteLLM's
``flatten_top_level_schema_combinators``: merge where merging is sound, and
pass a subschema through untouched when it is not.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "PROFILES",
    "Degradation",
    "ProviderProfile",
    "prepare",
    "profile_for",
]

_COMBINATORS = ("allOf", "oneOf", "anyOf")
_NUMERIC_CONSTRAINTS = (
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
)
_STRING_CONSTRAINTS = ("minLength", "maxLength", "pattern", "format")
_ARRAY_CONSTRAINTS = ("minItems", "maxItems", "uniqueItems")
_SEMANTIC_KEYWORDS = ("@context", "x-oold-iri", "x-oold-instance-rdf-type")


@dataclass
class Degradation:
    """What preparing a schema for one provider removed from it.

    Reported per arm and provider. A structured-output subset that loses most
    of a schema is a different condition from one that loses none, and saying
    so with a number is cheaper than arguing about it.
    """

    dropped: dict[str, int] = field(default_factory=dict)
    """Keyword to how many times it was removed."""
    refs_inlined: int = 0
    recursion_cut: int = 0
    """Subschemas replaced by a permissive stub because recursion was not
    supported and the cycle had to end somewhere."""
    made_required: int = 0
    constraints_described: int = 0
    """Constraints moved into ``description`` because the provider rejects
    them but the model can still read them."""
    semantics_dropped: int = 0
    """``@context`` and IRI keywords removed. This is the difference between a
    grounded arm and a flattened one."""
    keywords_before: int = 0
    keywords_after: int = 0

    @property
    def fidelity(self) -> float:
        """Share of the original keywords that survived, 1.0 when none were
        lost. Inlining a ``$ref`` duplicates keywords, so this can exceed 1.0;
        that is information preserved, not lost."""
        if not self.keywords_before:
            return 1.0
        return self.keywords_after / self.keywords_before

    def _note(self, keyword: str) -> None:
        self.dropped[keyword] = self.dropped.get(keyword, 0) + 1

    def describe(self) -> dict[str, Any]:
        return {
            "fidelity": round(self.fidelity, 4),
            "keywords_before": self.keywords_before,
            "keywords_after": self.keywords_after,
            "dropped": dict(sorted(self.dropped.items())),
            "refs_inlined": self.refs_inlined,
            "recursion_cut": self.recursion_cut,
            "made_required": self.made_required,
            "constraints_described": self.constraints_described,
            "semantics_dropped": self.semantics_dropped,
        }


@dataclass(frozen=True)
class ProviderProfile:
    """What one provider's structured-output mode accepts.

    Declared, never inferred from the model name. A substring test on a
    deployment name silently sends an OpenAI-compatible endpoint serving an
    open-weight model down the OpenAI branch.
    """

    name: str
    supports_combinators: bool = False
    """Whether ``allOf``, ``oneOf`` and ``not`` survive. Only a consumer that
    takes arbitrary JSON Schema keywords does; every strict structured-output
    mode rejects them."""
    supports_recursive_ref: bool = True
    supports_any_of: bool = True
    supports_numeric_constraints: bool = True
    supports_string_constraints: bool = True
    requires_all_properties_required: bool = False
    requires_additional_properties_false: bool = False
    max_optional_properties: int | None = None
    max_recursion_depth: int = 4
    """Where to cut a cycle when the provider cannot express one."""

    def accepts(self, keyword: str) -> bool:
        if keyword in ("allOf", "oneOf", "not"):
            return self.supports_combinators
        if keyword == "anyOf":
            return self.supports_any_of
        if keyword in _NUMERIC_CONSTRAINTS:
            return self.supports_numeric_constraints
        if keyword in _STRING_CONSTRAINTS:
            return self.supports_string_constraints
        return True


PROFILES: dict[str, ProviderProfile] = {
    "native": ProviderProfile(
        name="native",
        supports_combinators=True,
        supports_recursive_ref=True,
        supports_any_of=True,
        supports_numeric_constraints=True,
        supports_string_constraints=True,
    ),
    "openai": ProviderProfile(
        name="openai",
        supports_recursive_ref=True,
        supports_any_of=True,
        supports_numeric_constraints=True,
        supports_string_constraints=True,
        requires_all_properties_required=True,
        requires_additional_properties_false=True,
    ),
    "anthropic": ProviderProfile(
        name="anthropic",
        supports_recursive_ref=False,
        supports_any_of=False,
        supports_numeric_constraints=False,
        supports_string_constraints=False,
        requires_all_properties_required=False,
        requires_additional_properties_false=True,
        max_optional_properties=24,
    ),
    "google": ProviderProfile(
        name="google",
        supports_recursive_ref=True,
        supports_any_of=True,
        supports_numeric_constraints=True,
        supports_string_constraints=False,
        requires_all_properties_required=False,
        requires_additional_properties_false=False,
    ),
}
"""Declared subsets.

``native`` sends the schema through unchanged, which is the grounded arm: the
consumer takes arbitrary JSON Schema keywords and the ``@context`` is carried
through as grounding. The others are the strict structured-output subset, and
what each of them removes is the reason the two arms can differ.
"""


def profile_for(name: str) -> ProviderProfile:
    if name not in PROFILES:
        raise KeyError(
            f"unknown provider profile {name!r}, "
            f"expected one of {sorted(PROFILES)}"
        )
    return PROFILES[name]


def _count_keywords(node: Any) -> int:
    if isinstance(node, dict):
        return len(node) + sum(_count_keywords(v) for v in node.values())
    if isinstance(node, list):
        return sum(_count_keywords(v) for v in node)
    return 0


def _merge(into: dict[str, Any], other: dict[str, Any]) -> None:
    """Merge one subschema into another, union-ing the parts that union."""
    for key, value in other.items():
        if key == "properties":
            into.setdefault("properties", {}).update(value)
        elif key == "required":
            merged = list(into.get("required", [])) + list(value)
            into["required"] = sorted(set(merged))
        elif key not in into:
            into[key] = value


def _describe_constraint(node: dict[str, Any], keyword: str) -> None:
    """Fold a rejected constraint into the description, as the SDKs do."""
    note = f"{keyword}: {node[keyword]}"
    existing = node.get("description")
    node["description"] = f"{existing} ({note})" if existing else note


def prepare(
    schema: dict[str, Any],
    profile: ProviderProfile,
    *,
    grounding: bool = True,
) -> tuple[dict[str, Any], Degradation]:
    """Prepare a schema for one provider, and report what that cost.

    ``grounding`` keeps ``@context`` and the IRI keywords in place. Turning it
    off is the flattened structured-output subset, where the semantics survive
    only in ``title`` and ``description``.
    """
    report = Degradation()
    report.keywords_before = _count_keywords(schema)
    defs = {**schema.get("$defs", {}), **schema.get("definitions", {})}
    inlining = not profile.supports_combinators
    """Flattening combinators forces refs to be inlined, because a merged
    parent cannot stay behind a reference. A provider that keeps combinators
    keeps ``$defs`` and needs neither."""

    def _close_object(node: dict[str, Any]) -> dict[str, Any]:
        """Apply the object-level rules a provider imposes."""
        if node.get("type") != "object" and "properties" not in node:
            return node
        properties = node.get("properties") or {}
        if profile.requires_additional_properties_false:
            node["additionalProperties"] = False
        if profile.requires_all_properties_required and properties:
            optional = [
                k for k in properties if k not in node.get("required", [])
            ]
            report.made_required += len(optional)
            for key in optional:
                child = properties[key]
                if isinstance(child, dict) and "type" in child:
                    current = child["type"]
                    types = current if isinstance(current, list) else [current]
                    if "null" not in types:
                        child["type"] = [*types, "null"]
            node["required"] = list(properties)
        elif profile.max_optional_properties is not None and properties:
            required = node.get("required", [])
            optional = [k for k in properties if k not in required]
            overflow = len(optional) - profile.max_optional_properties
            if overflow > 0:
                for key in optional[-overflow:]:
                    properties.pop(key, None)
                    report._note("optional-property-overflow")
        return node

    def walk(node: Any, seen: tuple[str, ...], depth: int) -> Any:
        if isinstance(node, list):
            return [walk(item, seen, depth) for item in node]
        if not isinstance(node, dict):
            return node

        node = dict(node)

        ref = node.pop("$ref", None)
        if ref is not None:
            name = ref.rsplit("/", 1)[-1]
            recursing = name in seen
            too_deep = depth > profile.max_recursion_depth
            keep_ref = (
                # A consumer that takes arbitrary keywords keeps $defs too, so
                # there is nothing to inline and nothing is lost.
                not inlining
                or (recursing and profile.supports_recursive_ref and not too_deep)
            )
            if keep_ref:
                node["$ref"] = ref
                return node
            if name not in defs or too_deep or recursing:
                report.recursion_cut += 1
                return {
                    "type": "string",
                    "description": node.get(
                        "description", f"reference to {name}"
                    ),
                }
            report.refs_inlined += 1
            resolved = walk(defs[name], (*seen, name), depth + 1)
            if isinstance(resolved, dict):
                _merge(node, resolved)
            # The inlined body has been walked already, under a `seen` that
            # knows about this reference. Walking it again from here would not.
            return _close_object(node)

        for combinator in _COMBINATORS:
            if combinator not in node:
                continue
            if profile.accepts(combinator):
                node[combinator] = walk(node[combinator], seen, depth)
                continue
            branches = node.pop(combinator)
            report._note(combinator)
            if combinator == "allOf":
                for branch in branches:
                    resolved = walk(branch, seen, depth + 1)
                    if isinstance(resolved, dict):
                        _merge(node, resolved)
            elif branches:
                resolved = walk(branches[0], seen, depth + 1)
                if isinstance(resolved, dict):
                    _merge(node, resolved)

        if "not" in node:
            node.pop("not")
            report._note("not")

        for keyword in (*_NUMERIC_CONSTRAINTS, *_STRING_CONSTRAINTS):
            if keyword in node and not profile.accepts(keyword):
                _describe_constraint(node, keyword)
                node.pop(keyword)
                report.constraints_described += 1
                report._note(keyword)

        if not grounding:
            for keyword in _SEMANTIC_KEYWORDS:
                if keyword in node:
                    node.pop(keyword)
                    report.semantics_dropped += 1
                    report._note(keyword)

        for keyword in ("properties", "items", "prefixItems"):
            if keyword in node:
                node[keyword] = walk(node[keyword], seen, depth)
        for key, value in list(node.items()):
            if key in _COMBINATORS or key in ("properties", "items", "prefixItems"):
                continue
            if isinstance(value, (dict, list)) and key not in ("enum", "default"):
                node[key] = walk(value, seen, depth)

        return _close_object(node)

    prepared = walk(copy.deepcopy(schema), (), 0)
    if inlining and isinstance(prepared, dict):
        prepared.pop("$defs", None)
        prepared.pop("definitions", None)
    report.keywords_after = _count_keywords(prepared)
    return prepared, report


def schema_hash(schema: dict[str, Any]) -> str:
    """Stable hash of the schema actually sent, for the result record."""
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
