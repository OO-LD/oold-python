"""The registry of every check id the validator can emit.

Two identifier systems appear in a finding: the check id (``lint.container``) names which check
in this package produced it, and the rule id (``OOLD-RT-08f2``) names the normative statement it
enforces, when there is one. Rule ids come from the specification and are permanent; check ids
are implementation-defined and follow this package's structure. A finding cites both, because
fourteen of the thirty-nine checks enforce no rule at all - `schema.meta` is definitional,
`generate.satisfiable`, `variants` and the `roundtrip.*` checks are this validator's methodology,
`coverage.*` are self-tests about the fixture suite, `meta.self-check` and `rule.checks` report on
the run itself rather than on a schema, and `compliance.suite`/`compliance.*` are the deterministic
fixture suite's own outcomes - and for those the check id is the only identifier a user has.

This module holds two things that used to live apart. The twenty-one ``rule.*`` checks each
enforce exactly one normative statement and are narrow enough to be self-contained predicates,
so they are declared here and executed by :func:`run_rule_checks`. Most take an already-resolved
:class:`ContextView` and the schema exactly as authored (:attr:`CheckInfo.run`); a few instead
need the dereferenced schema, to see through an ancestor's `$ref` (:attr:`CheckInfo.run_resolved`).
The other eighteen checks are driven by the phases in ``pipeline.py`` and leave both empty; this
module only records their metadata; ``detects`` points at the function that actually decides the
verdict, where one function is clearly responsible.

Every check is written to avoid false positives in preference to catching every violation. A
validator that cries wolf on valid schemas gets switched off, and an unenforced rule is already
reported honestly by ``coverage.rules``.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

from .compliance import run_suite, vocabulary_coverage
from .formats import is_iri
from .frame import collect_composed_properties, instance_rdf_types
from .generate import generate
from .instance_checks import roundtrip_instance, validate_instance
from .meta_store import MetaBundle
from .pattern_lint import array_properties_missing_container, iri_references_missing_format
from .pattern_lint import lint as _lint_pattern
from .predicates import check_predicates
from .report import FAIL, OK, SKIP, WARN, Status
from .schema_checks import check_refs_resolve

#: A `$schema` naming the OO-LD dialect, on either canonical domain. The domain moved from
#: oo-ld.github.io to oo-ld.org, and released copies stamp a version in place of `latest`, so the
#: check matches the file name rather than any single URL.
_OOLD_META = re.compile(r"oold-meta-schema\.json$")

#: A canonical, hyphenated UUID, optionally prefixed with the `urn:uuid:` scheme. Version and
#: variant bits are not checked - the rule asks for "a UUID value", not a version 4 UUID.
_UUID = re.compile(r"^(?:urn:uuid:)?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

#: A permissive BCP 47 language tag: a 2-3 letter primary subtag, then any number of hyphenated
#: subtags of 1-8 alphanumeric characters. Permissive on purpose: the rule only asks that a key
#: "look like" a BCP 47 tag, and rejecting an unusual but legal subtag (script, region, variant,
#: extension) would be a false positive.
_BCP47_TAG = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8})*$")

#: JSON Schema 2020-12's own meta-schema URI - the REQUIRED floor `rule.dialect-version` checks
#: for, distinct from `rule.dialect` above, which additionally prefers the OO-LD dialect itself.
_JSON_SCHEMA_2020_12 = re.compile(r"^https?://json-schema\.org/draft/2020-12/schema/?#?$")


@dataclass
class RuleFinding:
    """One rule's outcome for one schema."""

    check_id: str
    rule: str
    status: Status
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextView:
    """A schema's *resolved* context, as the rules need to see it.

    Rules are about what an instance actually experiences, and OO-LD contexts inherit: a schema
    whose `@context` is `["Thing.schema.json", {...}]` gets `@version` and the `id` alias from
    Thing. Judging such a schema on its own literal `@context` reports violations that are not
    real, so every rule here is given the resolved form.
    """

    terms: dict[str, Any] = field(default_factory=dict)
    entries: list[Any] = field(default_factory=list)

    def keyword(self, name: str) -> Any:
        """The effective value of a context keyword such as ``@version``, or None."""
        for entry in self.entries:
            if isinstance(entry, dict) and name in entry:
                return entry[name]
        return None


#: A self-contained rule check: given a schema and its resolved context, the problems it found.
Predicate = Callable[[dict[str, Any], ContextView], list[str]]

#: RFC 2119 levels that make a violation a failure. Everything else is advice, so it warns.
_MUST_LEVELS = frozenset({"MUST", "MUST NOT", "SHALL", "SHALL NOT", "REQUIRED"})

#: Used only when the meta version in use ships no catalogue to read the level from.
DEFAULT_LEVEL: Status = FAIL


def severity(rule: dict[str, Any] | None, fallback: Status = DEFAULT_LEVEL) -> Status:
    """How hard a violation of this rule should land, taken from the specification.

    The level is the specification's own, not a taste judgement made here, so relaxing a MUST to
    a SHOULD upstream changes the validator's behaviour with no code change. Without a catalogue
    there is nothing to read, and the caller's fallback applies.
    """
    if not rule:
        return fallback
    return FAIL if rule.get("level") in _MUST_LEVELS else WARN


# ---------------------------------------------------------------------------- individual rules


def _missing_id(schema: dict[str, Any], context: ContextView) -> list[str]:
    if not schema.get("$id"):
        return ["schema declares no $id, so it has no global identifier"]
    return []


def _id_has_fragment(schema: dict[str, Any], context: ContextView) -> list[str]:
    identifier = schema.get("$id")
    if not isinstance(identifier, str) or "#" not in identifier:
        return []
    fragment = identifier.split("#", 1)[1]
    # An empty fragment is explicitly allowed; only a non-empty one is forbidden.
    return [f"$id carries a non-empty fragment: {identifier!r}"] if fragment else []


def _range_uses_ref(schema: dict[str, Any], context: ContextView) -> list[str]:
    """`x-oold-range` must reference with `x-oold-ref`, never `$ref`.

    A plain `$ref` inside a range would be eagerly dereferenced by a generic bundler, which for a
    cyclic schema graph is exactly the unbounded recursion OO-LD avoids by keeping range
    references lazy.
    """
    found: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f"{path}[{index}]")
            return
        if not isinstance(node, dict):
            return
        if "$ref" in node:
            found.append(f"{path} uses $ref; x-oold-range must use x-oold-ref")
        for key, value in node.items():
            if key != "$ref":
                walk(value, f"{path}/{key}")

    for name, prop in collect_composed_properties(schema).items():
        if isinstance(prop, dict) and isinstance(prop.get("x-oold-range"), (dict, list)):
            walk(prop["x-oold-range"], f"properties/{name}/x-oold-range")
    return found


def _inline_type_disagrees(schema: dict[str, Any], context: ContextView) -> list[str]:
    """An inline `type` must agree with the schema's declared `x-oold-instance-rdf-type`.

    Only a *pinned* type is checked - `const`, `default`, or a single-entry `enum`. An open
    `type: string` says nothing about what instances will carry, so it cannot disagree.
    """
    declared = instance_rdf_types(schema)
    if not declared:
        return []
    prop = collect_composed_properties(schema).get("type")
    if not isinstance(prop, dict):
        return []

    pinned: list[Any] = []
    for key in ("const", "default"):
        if key in prop:
            pinned = prop[key] if isinstance(prop[key], list) else [prop[key]]
            break
    else:
        enum = prop.get("enum")
        if isinstance(enum, list) and len(enum) == 1:
            pinned = enum if not isinstance(enum[0], list) else enum[0]

    if not pinned:
        return []
    stray = [t for t in pinned if t not in declared]
    if stray:
        return [f"the type property pins {stray!r}, which is absent from x-oold-instance-rdf-type {declared!r}"]
    return []


def _free_text_range_coerced_to_iri(schema: dict[str, Any], context: ContextView) -> list[str]:
    """A property whose range includes free text must not use ``@type: "@id"``.

    ``@type: "@id"`` coerces *every* string to an IRI, so free text becomes an often invalid IRI
    and is dropped. The property is only flagged when its own schema clearly admits a bare string
    alongside a non-string form, which is what "the range includes free text" means.
    """
    problems = []
    for name, prop in collect_composed_properties(schema).items():
        definition = context.terms.get(name)
        if not isinstance(definition, dict) or definition.get("@type") != "@id":
            continue
        if _admits_free_text(prop):
            problems.append(
                f"{name!r} admits a bare string but its term coerces every value with "
                '@type: "@id", so free text becomes an invalid IRI'
            )
    return problems


def _admits_free_text(prop: Any) -> bool:
    """True when a property permits a plain string *and* some other shape.

    A reference typed only as a string is the ordinary bare-IRI form and is correct; the
    violation is a property that mixes free text with references or embedded objects.
    """
    if not isinstance(prop, dict):
        return False
    for keyword in ("anyOf", "oneOf"):
        branches = prop.get(keyword)
        if not isinstance(branches, list) or len(branches) < 2:
            continue
        kinds = {b.get("type") for b in branches if isinstance(b, dict)}
        # A string branch with no `format` and no `x-oold-range` is free text rather than an IRI.
        text = any(
            isinstance(b, dict) and b.get("type") == "string" and not b.get("format") and "x-oold-range" not in b
            for b in branches
        )
        if text and kinds - {"string"}:
            return True
    return False


def _closed_object_rejects_metadata(schema: dict[str, Any], context: ContextView) -> list[str]:
    """A schema closing its objects must still permit `$schema` and `@context`.

    An instance carries both as ordinary members, so a schema with
    ``additionalProperties: false`` that does not declare them rejects its own conforming
    instances.
    """
    closed = schema.get("additionalProperties") is False or schema.get("unevaluatedProperties") is False
    if not closed:
        return []
    declared = set(collect_composed_properties(schema))
    missing = [key for key in ("$schema", "@context") if key not in declared]
    if missing:
        return [
            "the schema closes its objects but does not declare "
            + ", ".join(missing)
            + ", so a conforming instance carrying them would be rejected"
        ]
    return []


def _missing_version(schema: dict[str, Any], context: ContextView) -> list[str]:
    if not schema.get("x-oold-version"):
        return ["schema declares no x-oold-version"]
    return []


def _id_not_aliased(schema: dict[str, Any], context: ContextView) -> list[str]:
    """`@id` should be reachable through a variable-name-friendly alias."""
    if not context.terms:
        return []
    aliases = [t for t, d in context.terms.items() if (d.get("@id") if isinstance(d, dict) else d) == "@id"]
    if not aliases:
        return ["no @context term aliases @id, so instances must use the @id key directly"]
    return []


def _dialect_not_declared(schema: dict[str, Any], context: ContextView) -> list[str]:
    declared = schema.get("$schema")
    if not isinstance(declared, str) or not _OOLD_META.search(declared):
        return [f"$schema is {declared!r}, not the OO-LD dialect meta-schema"]
    return []


def _processing_mode_not_declared(schema: dict[str, Any], context: ContextView) -> list[str]:
    """`@version` must be the JSON number 1.1, not the string "1.1"."""
    value = context.keyword("@version")
    if value is None:
        return ['the resolved @context declares no "@version": 1.1']
    if value == 1.1 and not isinstance(value, str):
        return []
    return [f"@version is {value!r}; it must be the JSON number 1.1, not a string"]


def _uuid_annotation_missing_or_invalid(schema: dict[str, Any], context: ContextView) -> list[str]:
    """`x-oold-uuid`, if present, must actually be a UUID."""
    value = schema.get("x-oold-uuid")
    if value is None:
        return ["schema declares no x-oold-uuid annotation"]
    if not isinstance(value, str) or not _UUID.match(value):
        return [f"x-oold-uuid is {value!r}, which is not a UUID"]
    return []


def _multilang_missing_default(schema: dict[str, Any], context: ContextView) -> list[str]:
    """A schema using a multilingual keyword must still carry the plain default it falls back to.

    Only fires when the multilingual keyword is actually used - the word "still" in the rule is
    what scopes it; a schema using neither keyword says nothing about localization at all.
    """
    problems = []
    if "x-oold-multilang-title" in schema and "title" not in schema:
        problems.append("x-oold-multilang-title is present but the schema declares no default title")
    if "x-oold-multilang-description" in schema and "description" not in schema:
        problems.append("x-oold-multilang-description is present but the schema declares no default description")
    return problems


def _base_uri_misaligned(schema: dict[str, Any], context: ContextView) -> list[str]:
    """`$id` and the resolved `@base` should resolve a relative reference to the same place.

    Only judged when both are actually present: with no `@base` there is nothing on the JSON-LD
    side to compare against, and guessing which of the two is "correct" is not this check's job.
    """
    schema_id = schema.get("$id")
    if not isinstance(schema_id, str) or not schema_id:
        return []
    base = context.keyword("@base")
    if not base:
        return []

    probe = "Sibling.schema.json"
    under_schema = urljoin(schema_id, probe)
    under_jsonld = urljoin(urljoin(schema_id, base), probe)
    if under_schema == under_jsonld:
        return []
    return [
        f"$id ({schema_id!r}) and the resolved @base ({base!r}) are not aligned: a relative "
        f"reference resolves to {under_schema!r} under $id but {under_jsonld!r} under @base"
    ]


def _embedded_ref_missing_scoped_context(schema: dict[str, Any], context: ContextView) -> list[str]:
    """An object embedded by `$ref` to another document should get a scoped `@context`.

    Deliberately narrow: an inline `type: object` embed is not flagged, because the rule's own
    paragraph permits flattening those terms onto the root context for a cyclic embed graph, and
    this check cannot tell a cyclic graph from a careless one without resolving remote schemas. A
    `$ref` to the schema's own `$id` is exempted for the same reason - a self-reference cannot be
    given a scoped remote context without recursing.
    """
    own_id = schema.get("$id")
    problems = []
    for name, prop in collect_composed_properties(schema).items():
        target = _ref_embed_target(prop)
        if target is None:
            continue
        if own_id and target == own_id:
            continue
        definition = context.terms.get(name)
        if definition is None:
            continue  # no term at all: a different check covers ungrounded predicates
        if not isinstance(definition, dict) or "@context" in definition:
            continue
        problems.append(
            f"{name!r} brings in an embedded object by $ref ({target}) but its term declares no "
            "scoped @context, so the embedded schema's terms resolve globally. If the embed graph "
            "is cyclic this may be deliberate: the specification allows flattening onto the root "
            "context in that case."
        )
    return problems


def _ref_embed_target(prop: Any) -> str | None:
    """The `$ref` target when a property, or the `items` of an array property, embeds by reference.

    Only a direct `$ref`, or one nested inside a single-entry `allOf`, counts - the shapes that
    unambiguously mean "this property's value is another schema document". `x-oold-range` is not
    walked into: it denotes a scalar reference, not an embedded object.
    """
    if not isinstance(prop, dict):
        return None
    target = _ref_target(prop)
    if target:
        return target
    return _ref_target(prop.get("items")) if isinstance(prop.get("items"), dict) else None


def _ref_target(node: dict[str, Any]) -> str | None:
    if isinstance(node.get("$ref"), str):
        return node["$ref"]
    branches = node.get("allOf")
    if isinstance(branches, list) and len(branches) == 1 and isinstance(branches[0], dict):
        return _ref_target(branches[0])
    return None


def _multilang_shape_invalid(schema: dict[str, Any], context: ContextView) -> list[str]:
    """`x-oold-multilang-title`/`x-oold-multilang-description` map BCP 47 tags to strings."""
    problems: list[str] = []
    for key in ("x-oold-multilang-title", "x-oold-multilang-description"):
        value = schema.get(key)
        if value is None:
            continue
        if not isinstance(value, dict):
            problems.append(f"{key} is {value!r}, not an object mapping language tags to strings")
            continue
        for tag, text in value.items():
            if not _BCP47_TAG.match(tag):
                problems.append(f"{key} has key {tag!r}, which does not look like a BCP 47 language tag")
            if not isinstance(text, str):
                problems.append(f"{key}[{tag!r}] is {text!r}, not a string")
    return problems


def _dialect_not_2020_12(schema: dict[str, Any], context: ContextView) -> list[str]:
    """A declared `$schema` must be 2020-12-based: the REQUIRED floor, not merely preferred.

    Distinct from `rule.dialect` (OOLD-EXT-5184), a SHOULD that a schema declare the *OO-LD*
    dialect specifically. This one checks the REQUIRED floor underneath it: whatever dialect is
    declared must be JSON Schema 2020-12 itself, or the OO-LD dialect meta-schema (which is built
    on 2020-12). Skipped when `$schema` is absent - `rule.dialect` already reports that absence,
    and guessing a dialect here would double-report the same schema.
    """
    declared = schema.get("$schema")
    if not isinstance(declared, str) or not declared:
        return []
    if _OOLD_META.search(declared) or _JSON_SCHEMA_2020_12.match(declared):
        return []
    return [f"$schema is {declared!r}, which is not JSON Schema 2020-12 or the OO-LD dialect meta-schema"]


def _context_array_order_mismatched(schema: dict[str, Any], context: ContextView) -> list[str]:
    """`allOf`'s `$ref` targets must appear in `@context`, as an array, in the same order.

    Deliberately reads the literal schema rather than the resolved context, unlike most checks in
    this module: this rule is about whether the schema *as authored* stays directly usable as a
    remote `@context` without further processing, which is a statement about its own array and
    the order of its own entries, not about what a term means once resolution and inheritance are
    applied. So, on purpose, this predicate reads `schema["@context"]` and `schema["allOf"]`
    literally rather than taking the resolved `ContextView`.
    """
    allof = schema.get("allOf")
    if not isinstance(allof, list):
        return []
    targets = [entry["$ref"] for entry in allof if isinstance(entry, dict) and isinstance(entry.get("$ref"), str)]
    if len(targets) < 2:
        return []

    literal_context = schema.get("@context")
    if not isinstance(literal_context, list):
        return [
            f"allOf composes {len(targets)} remote contexts via $ref ({', '.join(targets)}) but "
            "@context is not an array, so this schema is not directly usable as a context"
        ]

    missing = [target for target in targets if target not in literal_context]
    if missing:
        return [f"@context does not list {target!r}, which allOf composes as a remote context" for target in missing]

    positions = [literal_context.index(target) for target in targets]
    if positions != sorted(positions):
        return [
            f"@context lists the allOf targets {targets!r} out of order (found at positions "
            f"{positions!r}); they must appear in the same order as the allOf members"
        ]
    return []


def _version_not_in_schema_location(schema: dict[str, Any], context: ContextView) -> list[str]:
    """`x-oold-version` should be part of the schema's location URL: OOLD-VER-534a.

    The catalogued `text` is the lead-in alone ("The version SHOULD be part of the schema's
    location:"); the URL forms it introduces are now `context`, and the two that state a
    requirement of their own were split into OOLD-VER-befc and OOLD-VER-4261 upstream. So this
    stays the umbrella check: it asks only that the version appear in the location, not which
    of the sanctioned layouts put it there. Deliberately - a validator cannot tell which layout
    a schema intends, and the third form, a GitHub release tag, is a shape of its own.

    Only judged when both `x-oold-version` and an absolute `$id` are present: `rule.version` and
    `rule.id` already cover their absence, and a relative `$id` names no location to carry a
    version.
    """
    version = schema.get("x-oold-version")
    identifier = schema.get("$id")
    if not isinstance(version, str) or not version:
        return []
    if not isinstance(identifier, str) or not is_iri(identifier):
        return []
    if version in identifier:
        return []
    return [f"x-oold-version {version!r} does not appear in the absolute $id {identifier!r}"]


def _root_ref_missing_from_context(schema: dict[str, Any], context: ContextView) -> list[str]:
    """A schema's single root-level `allOf` `$ref` must be reflected in its own `@context`.

    Deliberately reads the literal schema rather than the resolved context, for the same reason as
    `rule.context-array-order`: whether a schema stays directly usable as a remote `@context` with
    no further processing is a statement about its own, authored `@context`, not about what a term
    means once inheritance is applied. So this predicate reads `schema["@context"]` and
    `schema["allOf"]` literally, like that check does.

    `rule.context-array-order` (OOLD-CMP-e4a3) already covers two or more `allOf` `$ref`s and the
    order they must appear in, including reporting one that is missing entirely; this is the
    residue it never reaches, the single-`$ref` case, where there is no order to judge, only
    presence. `rule.scoped-context` (OOLD-CMP-5266) covers a property-level `$ref` separately, so
    only root-level composition is judged here.
    """
    allof = schema.get("allOf")
    if not isinstance(allof, list):
        return []
    targets = [entry["$ref"] for entry in allof if isinstance(entry, dict) and isinstance(entry.get("$ref"), str)]
    if len(targets) != 1:
        return []  # 0: nothing to reflect; 2+: rule.context-array-order's job

    target = targets[0]
    literal_context = schema.get("@context")
    if isinstance(literal_context, list) and target in literal_context:
        return []
    if isinstance(literal_context, str) and literal_context == target:
        return []
    if isinstance(literal_context, dict) and literal_context.get("@import") == target:
        return []
    return [
        f"allOf composes {target!r} as a remote context but @context does not reflect it, so this "
        "schema would need further processing before it can be interpreted as a JSON-LD context"
    ]


def _has_ref_branch(schema: dict[str, Any]) -> bool:
    """Whether `oneOf`/`anyOf` composes at least one branch by `$ref`."""
    for keyword in ("oneOf", "anyOf"):
        variants = schema.get(keyword)
        if not isinstance(variants, list):
            continue
        for variant in variants:
            if isinstance(variant, dict) and _ref_target(variant):
                return True
    return False


def _branch_context_conflict(schema: dict[str, Any], context: ContextView) -> list[str]:
    """Reflected `oneOf`/`anyOf` branch contexts must not conflict at the root.

    Scoped to schemas that actually compose `oneOf`/`anyOf` branches by `$ref` - only those have
    branch contexts that could be reflected at all; an inline branch (see `rule.free-text-iri`'s
    value-form examples) has no remote context of its own to conflict. A JSON-LD processor merges
    every `@context` array entry left to right with no notion of which branch an instance matched,
    so a root-level conflict would be decided by array order rather than by which branch the data
    actually conforms to.

    Only conflicts between *reflected* entries count. The specification separately allows a schema
    to "append its own context object as the last array entry to override an inherited term", and
    in the resolved view that override is indistinguishable from a conflict: the same term, two
    IRIs, two entries. What tells them apart is how the entry was authored - a string is a remote
    context reflected into the root, a dict is the schema's own object. `entries` keeps the
    authored order and length, resolving a reference in place, so the two line up by position and
    an override by the schema's own object is skipped rather than reported.
    """
    if not _has_ref_branch(schema):
        return []

    authored = schema.get("@context")
    authored = authored if isinstance(authored, list) else [authored]
    reflected = [not isinstance(entry, dict) for entry in authored]

    seen: dict[str, str] = {}
    problems: list[str] = []
    for position, entry in enumerate(context.entries):
        if not isinstance(entry, dict):
            continue
        # An entry the schema wrote itself may override anything above it; only a reflected
        # remote context can conflict in the sense this rule forbids.
        if position >= len(reflected) or not reflected[position]:
            continue
        for term, definition in entry.items():
            if term.startswith("@"):
                continue
            target = definition.get("@id") if isinstance(definition, dict) else definition
            if not isinstance(target, str):
                continue
            prior = seen.get(term)
            if prior is None:
                seen[term] = target
            elif prior != target:
                problems.append(f"{term!r} maps to both {prior!r} and {target!r} across the reflected @context")
    return problems


#: `maximum`/`exclusiveMaximum` and the three `max*` size bounds: a wider derived value relaxes
#: what an ancestor declared. `minimum`/`exclusiveMinimum` and the three `min*` bounds are the
#: mirror image, so they share the same comparison with the inequality flipped.
_WIDER_IF_GREATER = ("maximum", "exclusiveMaximum", "maxLength", "maxItems", "maxProperties")
_WIDER_IF_LESSER = ("minimum", "exclusiveMinimum", "minLength", "minItems", "minProperties")

#: Distinguishes "no node in the chain declares this keyword" from a legitimate `None`/`null`.
_MISSING = object()


def _numeric(value: Any) -> bool:
    """True for an `int`/`float` that is not also a `bool` (Python's `bool` is an `int`)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _chain_nodes(node: Any, seen: set[int] | None = None) -> Any:
    """Preorder walk of a resolved schema and its `allOf`-composed ancestors, root first.

    Same precedence as `collect_composed_properties`: a node's own declaration outranks
    anything reached through its `allOf`, and of several `allOf` entries the earlier one
    outranks the later. `seen` guards a self-referential chain defensively; `bound_schema`
    already cuts cycles before this ever runs, so in practice it never triggers.
    """
    if seen is None:
        seen = set()
    if not isinstance(node, dict) or id(node) in seen:
        return
    seen.add(id(node))
    yield node
    for sub in node.get("allOf") or []:
        yield from _chain_nodes(sub, seen)


def _first_declared(nodes: list[Any], keyword: str) -> tuple[Any, list[Any]]:
    """The most-derived value of `keyword` across `nodes`, and the nodes that follow it.

    `nodes` is ordered most-derived first, mirroring `_chain_nodes`. Under JSON Merge Patch a
    member is resolved independently per key, so the most-derived value for one keyword can come
    from a different chain position than another keyword on the very same property; this looks
    at one keyword at a time rather than at a whole property object. Returns `(_MISSING, [])`
    when no node declares the keyword at all.
    """
    for index, node in enumerate(nodes):
        if isinstance(node, dict) and keyword in node:
            return node[keyword], nodes[index + 1 :]
    return _MISSING, []


def _bound_relaxations(label: str, nodes: list[Any]) -> list[str]:
    """The two monotonic families: a derived bound must not be looser than an inherited one."""
    problems: list[str] = []
    for keyword in _WIDER_IF_GREATER:
        derived, ancestors = _first_declared(nodes, keyword)
        if derived is _MISSING or not _numeric(derived):
            continue
        for ancestor in ancestors:
            if not isinstance(ancestor, dict) or keyword not in ancestor:
                continue
            value = ancestor[keyword]
            if _numeric(value) and derived > value:
                problems.append(f"{label} relaxes {keyword} from {value!r} (inherited) to {derived!r}")
    for keyword in _WIDER_IF_LESSER:
        derived, ancestors = _first_declared(nodes, keyword)
        if derived is _MISSING or not _numeric(derived):
            continue
        for ancestor in ancestors:
            if not isinstance(ancestor, dict) or keyword not in ancestor:
                continue
            value = ancestor[keyword]
            if _numeric(value) and derived < value:
                problems.append(f"{label} relaxes {keyword} from {value!r} (inherited) to {derived!r}")
    return problems


def _multiple_of_relaxations(label: str, nodes: list[Any]) -> list[str]:
    """A derived `multipleOf` must itself be a multiple of an inherited one."""
    derived, ancestors = _first_declared(nodes, "multipleOf")
    if derived is _MISSING or not _numeric(derived) or derived <= 0:
        return []
    problems: list[str] = []
    for ancestor in ancestors:
        if not isinstance(ancestor, dict) or "multipleOf" not in ancestor:
            continue
        value = ancestor["multipleOf"]
        if not _numeric(value) or value <= 0:
            continue
        ratio = derived / value
        if not math.isclose(ratio, round(ratio), rel_tol=1e-9, abs_tol=1e-9):
            problems.append(
                f"{label} sets multipleOf {derived!r}, which is not itself a multiple of the inherited {value!r}"
            )
    return problems


def _enum_relaxations(label: str, nodes: list[Any]) -> list[str]:
    """A derived `enum` must not admit a value the inherited `enum` excluded."""
    derived, ancestors = _first_declared(nodes, "enum")
    if derived is _MISSING or not isinstance(derived, list):
        return []
    problems: list[str] = []
    for ancestor in ancestors:
        if not isinstance(ancestor, dict) or not isinstance(ancestor.get("enum"), list):
            continue
        missing = [value for value in derived if value not in ancestor["enum"]]
        if missing:
            problems.append(f"{label} enum admits {missing!r}, absent from the inherited enum {ancestor['enum']!r}")
    return problems


def _const_relaxations(label: str, nodes: list[Any]) -> list[str]:
    """A derived `const` must agree with an inherited `const`, or fall inside an inherited `enum`."""
    derived, ancestors = _first_declared(nodes, "const")
    if derived is _MISSING:
        return []
    problems: list[str] = []
    for ancestor in ancestors:
        if not isinstance(ancestor, dict):
            continue
        if "const" in ancestor:
            if ancestor["const"] != derived:
                problems.append(f"{label} const {derived!r} disagrees with the inherited const {ancestor['const']!r}")
        elif isinstance(ancestor.get("enum"), list) and derived not in ancestor["enum"]:
            problems.append(f"{label} const {derived!r} is absent from the inherited enum {ancestor['enum']!r}")
    return problems


def _type_set(value: Any) -> set[str] | None:
    """`type`, normalised to a set: a single string, or 2020-12's array-of-types form."""
    if isinstance(value, str):
        return {value}
    if isinstance(value, list) and value and all(isinstance(item, str) for item in value):
        return set(value)
    return None


def _type_relaxations(label: str, nodes: list[Any]) -> list[str]:
    """A derived `type` must not admit a JSON type absent from an inherited `type`."""
    derived, ancestors = _first_declared(nodes, "type")
    if derived is _MISSING:
        return []
    derived_types = _type_set(derived)
    if derived_types is None:
        return []
    problems: list[str] = []
    for ancestor in ancestors:
        if not isinstance(ancestor, dict) or "type" not in ancestor:
            continue
        ancestor_types = _type_set(ancestor["type"])
        if ancestor_types is None:
            continue
        stray = sorted(derived_types - ancestor_types)
        if stray:
            problems.append(
                f"{label} admits type(s) {stray!r}, absent from the inherited type {sorted(ancestor_types)!r}"
            )
    return problems


def _unique_items_relaxations(label: str, nodes: list[Any]) -> list[str]:
    """A derived `uniqueItems: false` must not relax an inherited `uniqueItems: true`."""
    derived, ancestors = _first_declared(nodes, "uniqueItems")
    if derived is not False:
        return []
    for ancestor in ancestors:
        if isinstance(ancestor, dict) and ancestor.get("uniqueItems") is True:
            return [f"{label} sets uniqueItems: false, relaxing the inherited uniqueItems: true"]
    return []


def _additional_properties_relaxations(label: str, nodes: list[Any]) -> list[str]:
    """A derived `additionalProperties: true` must not relax an inherited `additionalProperties: false`."""
    derived, ancestors = _first_declared(nodes, "additionalProperties")
    if derived is not True:
        return []
    for ancestor in ancestors:
        if isinstance(ancestor, dict) and ancestor.get("additionalProperties") is False:
            return [f"{label} sets additionalProperties: true, relaxing the inherited additionalProperties: false"]
    return []


def _relaxations(label: str, nodes: list[Any]) -> list[str]:
    """Every narrow-only comparison this check makes, for one member position.

    `label` names that position in a finding (a property, or the schema itself); `nodes` is its
    declarations across the chain, most-derived first.
    """
    return [
        *_bound_relaxations(label, nodes),
        *_multiple_of_relaxations(label, nodes),
        *_enum_relaxations(label, nodes),
        *_const_relaxations(label, nodes),
        *_type_relaxations(label, nodes),
        *_unique_items_relaxations(label, nodes),
        *_additional_properties_relaxations(label, nodes),
    ]


def _narrow_only_relaxations(schema: dict[str, Any], context: ContextView) -> list[str]:
    """A derived schema's assertion-bearing keywords may only tighten an ancestor's, never relax
    them: OOLD-CMP-f3c7.

    Takes the *resolved* schema (see `CheckInfo.run_resolved`): the raw, authored document
    composes an ancestor with `allOf: [{"$ref": ...}]`, and the ancestor's own constraints are
    not visible without resolving that reference first. After dereferencing, a subclass chain is
    inlined as nested `allOf` entries each carrying the ancestor's own `properties` - see
    `resolve.dereference`/`resolve.bound_schema` and `collect_composed_properties`'s docstring.

    Comparisons are per keyword rather than per whole property object, because that is how
    OO-LD's own merge model (JSON Merge Patch, RFC 7396) resolves the chain: keyed by object
    member, so `properties.foo.maximum` and `properties.foo.minimum` are each independently
    overridden by the nearest declaration, and can come from different levels of the same chain.
    The schema root itself is compared the same way, alongside each property, since a keyword
    such as `additionalProperties` sits there rather than under `properties`. `type` is compared
    as a set, since 2020-12 allows an array of types.

    Two keywords in the specification's own list are deliberately left out:

    - `pattern` - whether one regular expression is narrower than another is not decidable in
      general, so any comparison here would be a guess, not a finding.
    - `required` - an object-level keyword rather than an assertion on a single value. Under the
      merge model a derived object can legitimately drop an inherited `required` entry (that key
      simply stops being required), and the rule's own wording, about restricting a
      "constraint", does not clearly cover this case either way. Left unchecked rather than
      guessed.

    Only compares a keyword when both sides declare it with a comparable type - a `maximum` that
    is a string on either side, for instance, is silently skipped rather than compared.
    """
    nodes = list(_chain_nodes(schema))
    if len(nodes) < 2:
        return []  # no ancestor at all: nothing could have been relaxed

    problems = _relaxations("the schema itself", nodes)

    names: dict[str, None] = {}
    for node in nodes:
        for name in node.get("properties") or {}:
            names.setdefault(name, None)
    for name in names:
        property_nodes = [(node.get("properties") or {}).get(name) for node in nodes]
        problems.extend(_relaxations(f"property {name!r}", property_nodes))
    return problems


# ---------------------------------------------------------------------------- the registry


@dataclass(frozen=True)
class CheckInfo:
    """Metadata for one check id the validator can emit.

    ``detects`` holds the function object, never a string path, so a rename is followed rather
    than silently going stale. It is left ``None`` where a check has no single detection site -
    several report lines from different branches, or two functions that jointly decide one
    verdict - rather than pointing at one of several candidates and misleading a reader.

    ``default_status`` is what a violation reports when no rule applies: either the check enforces
    none, or the meta version in use ships no catalogue to read a level from. Where a rule and a
    catalogue are both available, severity comes from the rule's level instead (:func:`severity`).

    ``predates_catalog`` matters only when ``rule`` is set. Wherever a catalogue is available for
    the selected version, both values behave identically: the check runs only if the catalogue
    states the rule and has not deprecated it (see :func:`catalog_gate`). They differ only when a
    version ships no catalogue at all (0.7.0, 0.8.0): ``False``, the default, skips the check,
    because a rule minted after the catalogue cannot be attributed to a version that predates it.
    ``True`` runs it anyway, for the four checks whose requirement is older than the catalogue
    itself and would otherwise silently stop being enforced on those versions.

    ``run`` and ``run_resolved`` are mutually exclusive ways to be a self-contained rule check;
    at most one is set. ``run`` receives the schema exactly as authored, which is what a check
    reading its own literal ``@context``/``allOf`` needs (see ``rule.context-array-order`` and
    friends). ``run_resolved`` instead receives the dereferenced, bounded schema - the same one
    the pipeline already builds for generation and round-tripping - for a check that needs to see
    through an ancestor's ``$ref`` rather than just its own authored document.
    """

    id: str
    summary: str
    rule: str | None = None
    default_status: Status = FAIL
    per_version: bool = False
    detects: Callable[..., Any] | None = None
    run: Predicate | None = None
    run_resolved: Predicate | None = None
    predates_catalog: bool = False


CHECKS: tuple[CheckInfo, ...] = (
    # -------------------------------------------------------------- run setup
    CheckInfo(
        "meta.self-check",
        "the vendored meta-schema documents for one version are themselves well-formed",
        per_version=True,
        detects=MetaBundle.self_check,
    ),
    # -------------------------------------------------------------- schema well-formedness
    CheckInfo(
        "schema.meta",
        "a schema validates against the OO-LD meta-schema and can be compiled as a validator",
        per_version=True,
        # Two functions jointly decide this verdict (meta-schema validity, then compilability),
        # so there is no single detection site to point at.
        detects=None,
    ),
    CheckInfo(
        "schema.refs",
        "a schema's $ref composition resolves",
        detects=check_refs_resolve,
    ),
    # -------------------------------------------------------------- round-trip-safe pattern lint
    CheckInfo(
        "lint.pattern",
        "no @context term coerces a literal to a datatype JSON encodes natively",
        rule="OOLD-RT-d9bd",
        per_version=True,
        detects=_lint_pattern,
        predates_catalog=True,
    ),
    CheckInfo(
        "lint.container",
        "a strictly array-typed property declares @container @set or @list",
        rule="OOLD-RT-08f2",
        detects=array_properties_missing_container,
        predates_catalog=True,
    ),
    CheckInfo(
        "lint.iri-format",
        "a bare-IRI-string reference declares an iri-reference or stricter uri* format",
        rule="OOLD-EXT-6ea3",
        default_status=WARN,
        detects=iri_references_missing_format,
        predates_catalog=True,
    ),
    # -------------------------------------------------------------- generation and round-trip
    CheckInfo(
        "generate.satisfiable",
        "a generated instance validates against its own schema",
        detects=generate,
    ),
    CheckInfo(
        "roundtrip.generated",
        "a generated instance survives instance to RDF to instance with no property lost",
        # Reports SKIP for a cyclic context, FAIL for a processing error, FAIL for a shape
        # mismatch, and OK, from five separate call sites; none of them is *the* detection site.
        detects=None,
    ),
    CheckInfo(
        "context.remote",
        "a schema works as a remote @context",
        # Decided inline by a direct jsonld.expand() call, not by a function in a detection
        # module.
        detects=None,
    ),
    CheckInfo(
        "context.predicates",
        "every declared property produces a grounded predicate",
        rule="OOLD-EXT-2b61",
        detects=check_predicates,
        predates_catalog=True,
    ),
    CheckInfo(
        "variants",
        "each oneOf/anyOf branch is generated and round-tripped in turn",
        # Multiple emission sites inline in the pipeline's per-variant loop, mirroring
        # roundtrip.generated.
        detects=None,
    ),
    # -------------------------------------------------------------- instances
    CheckInfo(
        "instance.schema",
        "a committed instance validates against its schema",
        detects=validate_instance,
    ),
    CheckInfo(
        "roundtrip.instance",
        "an instance round-trips through RDF unchanged",
        detects=roundtrip_instance,
    ),
    # -------------------------------------------------------------- compliance-suite self-checks
    CheckInfo(
        "compliance.suite",
        "the compliance suite's own fixture files are readable and well-shaped",
        per_version=True,
        detects=run_suite,
    ),
    CheckInfo(
        "compliance.*",
        "one compliance-suite case produced the outcome its fixture expects",
        per_version=True,
        # One id per fixture "kind" (vocab, lint, validate, rdf, roundtrip, error, ...), built as
        # f"compliance.{case.kind}" from data in the fixture files rather than from code, so there
        # is no single detection site and no fixed set of kinds to enumerate. This entry stands
        # for the whole family; see the module docstring in `compliance.py`.
        detects=None,
    ),
    CheckInfo(
        "coverage.vocab",
        "every keyword the meta-schemas define has a well-formedness test",
        per_version=True,
        detects=vocabulary_coverage,
    ),
    CheckInfo(
        "coverage.rules",
        "every machine-checkable rule in the catalog is enforced by some check",
        default_status=WARN,
        per_version=True,
        # Compares the catalogue against this very registry; there is no external function to
        # point at.
        detects=None,
    ),
    # -------------------------------------------------------------- single-rule checks
    CheckInfo(
        "rule.checks",
        "the rule.* family as a whole, reported once when the selected meta-schema version ships "
        "no rule catalogue to attribute individual findings to",
        per_version=True,
        default_status=SKIP,
        # Decided inline in pipeline.py's `_run_rule_checks`, which substitutes this one finding
        # for the whole family rather than calling any of the predicates below.
        detects=None,
    ),
    CheckInfo(
        "rule.id",
        "a schema has a $id",
        rule="OOLD-VER-3b96",
        per_version=True,
        run=_missing_id,
    ),
    CheckInfo(
        "rule.id-fragment",
        "a $id has no non-empty fragment",
        rule="OOLD-CMP-dd2b",
        per_version=True,
        run=_id_has_fragment,
    ),
    CheckInfo(
        "rule.range-ref",
        "x-oold-range references use x-oold-ref",
        rule="OOLD-EXT-3fe9",
        per_version=True,
        run=_range_uses_ref,
    ),
    CheckInfo(
        "rule.instance-type",
        "a pinned type agrees with x-oold-instance-rdf-type",
        rule="OOLD-INS-4b5c",
        per_version=True,
        run=_inline_type_disagrees,
    ),
    CheckInfo(
        "rule.free-text-iri",
        "a free-text range is not coerced to @id",
        rule="OOLD-INS-2e5d",
        per_version=True,
        run=_free_text_range_coerced_to_iri,
    ),
    CheckInfo(
        "rule.closed-object",
        "a closed object still permits $schema and @context",
        rule="OOLD-INS-ba9e",
        per_version=True,
        run=_closed_object_rejects_metadata,
    ),
    CheckInfo(
        "rule.version",
        "a schema states x-oold-version",
        rule="OOLD-VER-3662",
        per_version=True,
        run=_missing_version,
    ),
    CheckInfo(
        "rule.id-alias",
        "@id is exposed through an alias",
        rule="OOLD-INS-2b3f",
        per_version=True,
        run=_id_not_aliased,
    ),
    CheckInfo(
        "rule.dialect",
        "a schema declares the OO-LD dialect",
        rule="OOLD-EXT-5184",
        per_version=True,
        run=_dialect_not_declared,
    ),
    CheckInfo(
        "rule.processing-mode",
        "a context declares @version 1.1",
        rule="OOLD-EXT-ddda",
        per_version=True,
        run=_processing_mode_not_declared,
    ),
    CheckInfo(
        "rule.uuid",
        "a schema carries an x-oold-uuid annotation holding a UUID value",
        rule="OOLD-VER-edb9",
        per_version=True,
        run=_uuid_annotation_missing_or_invalid,
    ),
    CheckInfo(
        "rule.multilang-default",
        "a schema using x-oold-multilang-title/description also declares the plain default",
        rule="OOLD-EXT-dd76",
        per_version=True,
        run=_multilang_missing_default,
    ),
    CheckInfo(
        "rule.base-alignment",
        "a schema's $id and resolved @base resolve a relative reference the same way",
        rule="OOLD-CMP-53bf",
        per_version=True,
        run=_base_uri_misaligned,
    ),
    CheckInfo(
        "rule.scoped-context",
        "an embedded object brought in by $ref is reflected as that property's scoped @context",
        rule="OOLD-CMP-5266",
        per_version=True,
        run=_embedded_ref_missing_scoped_context,
    ),
    CheckInfo(
        "rule.multilang-shape",
        "x-oold-multilang-title/description map BCP 47 language tags to translated strings",
        rule="OOLD-EXT-ef09",
        per_version=True,
        run=_multilang_shape_invalid,
    ),
    CheckInfo(
        "rule.dialect-version",
        "a declared $schema is JSON Schema 2020-12 or the OO-LD dialect built on it",
        rule="OOLD-EXT-af50",
        per_version=True,
        run=_dialect_not_2020_12,
    ),
    CheckInfo(
        "rule.context-array-order",
        "allOf's $ref targets appear in @context, as an array, in the same order",
        rule="OOLD-CMP-e4a3",
        per_version=True,
        run=_context_array_order_mismatched,
    ),
    CheckInfo(
        "rule.versioned-id",
        "x-oold-version is part of an absolute $id",
        rule="OOLD-VER-534a",
        per_version=True,
        run=_version_not_in_schema_location,
    ),
    CheckInfo(
        "rule.context-reflects-refs",
        "a single root-level allOf $ref is reflected in @context",
        rule="OOLD-CMP-b926",
        per_version=True,
        run=_root_ref_missing_from_context,
    ),
    CheckInfo(
        "rule.branch-context-conflict",
        "reflected oneOf/anyOf branch contexts do not conflict at the root",
        rule="OOLD-CMP-1d7e",
        per_version=True,
        run=_branch_context_conflict,
    ),
    CheckInfo(
        "rule.narrow-only",
        "a derived schema's assertion-bearing keywords only tighten what an allOf ancestor declared",
        rule="OOLD-CMP-f3c7",
        per_version=True,
        run_resolved=_narrow_only_relaxations,
    ),
)


def info(check_id: str) -> CheckInfo | None:
    """The registry entry for a check id, or None when it is not registered."""
    return _BY_ID.get(check_id)


def rule_for(check_id: str) -> str | None:
    """The rule a check enforces, or None when it enforces no single rule."""
    entry = _BY_ID.get(check_id)
    return entry.rule if entry else None


def rule_map() -> dict[str, str]:
    """check id -> rule id, for every check that enforces exactly one rule."""
    return {c.id: c.rule for c in CHECKS if c.rule}


_BY_ID: dict[str, CheckInfo] = {c.id: c for c in CHECKS}


def catalog_gate(check: CheckInfo, catalog: dict[str, dict[str, Any]] | None) -> RuleFinding | None:
    """Whether ``check`` must be skipped against ``catalog``, or None to mean "run it".

    This is the one place the presence/deprecation gating lives, shared by the self-contained
    ``rule.*`` predicates (via :func:`run_rule_checks`) and the four checks that predate the
    catalogue, applied directly in ``pipeline.py``. A check with no ``rule`` is never gated: the
    question only makes sense for a check that names a normative statement.

    ``catalog`` maps rule id to its catalogue entry for the meta version in use, or is None when
    that version ships no catalogue at all. Wherever a catalogue *is* present the two outcomes are
    identical regardless of :attr:`CheckInfo.predates_catalog`: skip if the rule is absent or
    deprecated, run otherwise. The field only changes what happens with no catalogue at all, which
    is the one thing a pre-catalogue version cannot state either way.
    """
    if check.rule is None:
        return None
    if catalog is None:
        if check.predates_catalog:
            return None
        return RuleFinding(
            check.id,
            check.rule,
            SKIP,
            f"{check.rule} cannot be attributed to this meta-schema version, which ships no rule catalogue",
        )
    rule = catalog.get(check.rule)
    if rule is None:
        return RuleFinding(
            check.id,
            check.rule,
            SKIP,
            f"{check.rule} is not stated by this meta-schema version",
        )
    if rule.get("deprecated"):
        superseded = ", ".join(rule.get("superseded_by") or []) or "nothing"
        return RuleFinding(
            check.id,
            check.rule,
            SKIP,
            f"{check.rule} is deprecated in this version (superseded by {superseded})",
        )
    return None


def run_rule_checks(
    schema: dict[str, Any],
    context: ContextView,
    catalog: dict[str, dict[str, Any]] | None = None,
    resolved: dict[str, Any] | None = None,
) -> list[RuleFinding]:
    """Apply the rule checks that the selected specification version actually states.

    ``catalog`` maps rule id to its catalogue entry for the meta version in use. When given, a
    check whose rule is absent from it is **skipped**: that version never stated the requirement,
    and enforcing it would report a violation of something the target does not require. A
    deprecated rule is skipped for the same reason from the other end. See :func:`catalog_gate`.

    When ``catalog`` is None the version ships no catalogue at all, and every one of these checks
    skips: none of them predates the catalogue (:attr:`CheckInfo.predates_catalog` is False for
    all of them), so there is nothing pre-catalogue evidence could attribute the rule to.

    ``resolved`` is the dereferenced, bounded schema, for the checks declared with
    :attr:`CheckInfo.run_resolved` rather than :attr:`CheckInfo.run`. When it is not available -
    the default, for callers with nothing to offer - a ``run_resolved`` check is skipped rather
    than guessing from the raw document or crashing on a missing argument.
    """
    findings: list[RuleFinding] = []
    for check in (c for c in CHECKS if c.run or c.run_resolved):
        gate = catalog_gate(check, catalog)
        if gate is not None:
            findings.append(gate)
            continue
        rule = (catalog or {}).get(check.rule)
        if check.run_resolved is not None:
            if resolved is None:
                findings.append(
                    RuleFinding(
                        check.id,
                        check.rule,
                        SKIP,
                        f"the dereferenced schema is not available in this context, so {check.rule} cannot be judged",
                    )
                )
                continue
            problems = check.run_resolved(resolved, context)
        else:
            problems = check.run(schema, context)
        if not problems:
            findings.append(RuleFinding(check.id, check.rule, OK))
        else:
            findings.append(
                RuleFinding(
                    check.id,
                    check.rule,
                    severity(rule, check.default_status),
                    "; ".join(problems),
                    {"problems": problems},
                )
            )
    return findings
