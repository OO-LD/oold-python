"""Checks implementing individual normative rules from the specification catalog.

The general-workflow checks ported from the reference harness each assert a broad property -
"the schema is well formed", "the instance round-trips". This module holds the narrower checks,
each enforcing exactly one statement in the specification and citing its rule id.

Keeping them together, declared rather than hand-wired, means the mapping from check to rule is
visible in one place and `coverage.rules` can be trusted: a rule appears as enforced only when a
check here actually implements it.

Every check is written to avoid false positives in preference to catching every violation. A
validator that cries wolf on valid schemas gets switched off, and an unenforced rule is already
reported honestly by `coverage.rules`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .frame import collect_composed_properties, instance_rdf_types
from .report import FAIL, OK, SKIP, WARN, Status

#: A `$schema` naming the OO-LD dialect, on either canonical domain. The domain moved from
#: oo-ld.github.io to oo-ld.org, and released copies stamp a version in place of `latest`, so the
#: check matches the file name rather than any single URL.
_OOLD_META = re.compile(r"oold-meta-schema\.json$")


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


@dataclass
class RuleCheck:
    """A check that enforces exactly one rule."""

    check_id: str
    rule: str
    describe: str
    run: Callable[[dict[str, Any], ContextView], list[str]]

    def __call__(
        self,
        schema: dict[str, Any],
        context: ContextView,
        rule: dict[str, Any] | None = None,
    ) -> RuleFinding:
        """Apply the check, taking its severity from ``rule`` when a catalogue supplied one."""
        problems = self.run(schema, context)
        if not problems:
            return RuleFinding(self.check_id, self.rule, OK)
        return RuleFinding(self.check_id, self.rule, severity(rule), "; ".join(problems), {"problems": problems})


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


# ---------------------------------------------------------------------------- registry

#: Every rule this package enforces beyond the ported general-workflow checks. Order is the order
#: findings are reported in.
RULE_CHECKS: list[RuleCheck] = [
    RuleCheck("rule.id", "OOLD-VER-001", "a schema has a $id", _missing_id),
    RuleCheck("rule.id-fragment", "OOLD-CMP-005", "a $id has no non-empty fragment", _id_has_fragment),
    RuleCheck("rule.range-ref", "OOLD-EXT-005", "x-oold-range references use x-oold-ref", _range_uses_ref),
    RuleCheck(
        "rule.instance-type",
        "OOLD-INS-002",
        "a pinned type agrees with x-oold-instance-rdf-type",
        _inline_type_disagrees,
    ),
    RuleCheck(
        "rule.free-text-iri",
        "OOLD-INS-009",
        "a free-text range is not coerced to @id",
        _free_text_range_coerced_to_iri,
    ),
    RuleCheck(
        "rule.closed-object",
        "OOLD-INS-005",
        "a closed object still permits $schema and @context",
        _closed_object_rejects_metadata,
    ),
    RuleCheck("rule.version", "OOLD-VER-002", "a schema states x-oold-version", _missing_version),
    RuleCheck("rule.id-alias", "OOLD-INS-007", "@id is exposed through an alias", _id_not_aliased),
    RuleCheck("rule.dialect", "OOLD-EXT-002", "a schema declares the OO-LD dialect", _dialect_not_declared),
    RuleCheck("rule.processing-mode", "OOLD-EXT-001", "a context declares @version 1.1", _processing_mode_not_declared),
]

#: check id -> rule id, for the pipeline's citation mapping and coverage figure.
RULE_CHECK_MAP: dict[str, str] = {c.check_id: c.rule for c in RULE_CHECKS}


def run_rule_checks(
    schema: dict[str, Any],
    context: ContextView,
    catalog: dict[str, dict[str, Any]] | None = None,
) -> list[RuleFinding]:
    """Apply the rule checks that the selected specification version actually states.

    ``catalog`` maps rule id to its catalogue entry for the meta version in use. When given, a
    check whose rule is absent from it is **skipped**: that version never stated the requirement,
    and enforcing it would report a violation of something the target does not require. A
    deprecated rule is skipped for the same reason from the other end.

    When ``catalog`` is None the version ships no catalogue at all, and the caller decides
    whether to run the checks blind or skip them.
    """
    findings: list[RuleFinding] = []
    for check in RULE_CHECKS:
        rule = (catalog or {}).get(check.rule)
        if catalog is not None:
            if rule is None:
                findings.append(
                    RuleFinding(
                        check.check_id,
                        check.rule,
                        SKIP,
                        f"{check.rule} is not stated by this meta-schema version",
                    )
                )
                continue
            if rule.get("deprecated"):
                superseded = ", ".join(rule.get("superseded_by") or []) or "nothing"
                findings.append(
                    RuleFinding(
                        check.check_id,
                        check.rule,
                        SKIP,
                        f"{check.rule} is deprecated in this version (superseded by {superseded})",
                    )
                )
                continue
        findings.append(check(schema, context, rule))
    return findings
