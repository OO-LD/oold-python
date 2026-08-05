"""The registry of every check id the validator can emit.

Two identifier systems appear in a finding: the check id (``lint.container``) names which check
in this package produced it, and the rule id (``OOLD-RT-002``) names the normative statement it
enforces, when there is one. Rule ids come from the specification and are permanent; check ids
are implementation-defined and follow this package's structure. A finding cites both, because
fourteen of the twenty-eight checks enforce no rule at all - `schema.meta` is definitional,
`generate.satisfiable`, `variants` and the `roundtrip.*` checks are this validator's methodology,
`coverage.*` are self-tests about the fixture suite, `meta.self-check` and `rule.checks` report on
the run itself rather than on a schema, and `compliance.suite`/`compliance.*` are the deterministic
fixture suite's own outcomes - and for those the check id is the only identifier a user has.

This module holds two things that used to live apart. The ten ``rule.*`` checks each enforce
exactly one normative statement and are narrow enough to be self-contained predicates over an
already-resolved :class:`ContextView`, so they are declared here and executed by
:func:`run_rule_checks`. The other eighteen checks are driven by the phases in ``pipeline.py`` and
leave :attr:`CheckInfo.run` empty; this module only records their metadata; ``detects`` points at
the function that actually decides the verdict, where one function is clearly responsible.

Every check is written to avoid false positives in preference to catching every violation. A
validator that cries wolf on valid schemas gets switched off, and an unenforced rule is already
reported honestly by ``coverage.rules``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .compliance import run_suite, vocabulary_coverage
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
    """

    id: str
    summary: str
    rule: str | None = None
    default_status: Status = FAIL
    per_version: bool = False
    detects: Callable[..., Any] | None = None
    run: Predicate | None = None
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
        rule="OOLD-RT-001",
        per_version=True,
        detects=_lint_pattern,
        predates_catalog=True,
    ),
    CheckInfo(
        "lint.container",
        "a strictly array-typed property declares @container @set or @list",
        rule="OOLD-RT-002",
        detects=array_properties_missing_container,
        predates_catalog=True,
    ),
    CheckInfo(
        "lint.iri-format",
        "a bare-IRI-string reference declares an iri-reference or stricter uri* format",
        rule="OOLD-EXT-006",
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
        rule="OOLD-EXT-007",
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
        "every checkable rule in the catalog is enforced by some check",
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
        # for the whole family rather than calling any of the ten predicates below.
        detects=None,
    ),
    CheckInfo(
        "rule.id",
        "a schema has a $id",
        rule="OOLD-VER-001",
        per_version=True,
        run=_missing_id,
    ),
    CheckInfo(
        "rule.id-fragment",
        "a $id has no non-empty fragment",
        rule="OOLD-CMP-005",
        per_version=True,
        run=_id_has_fragment,
    ),
    CheckInfo(
        "rule.range-ref",
        "x-oold-range references use x-oold-ref",
        rule="OOLD-EXT-005",
        per_version=True,
        run=_range_uses_ref,
    ),
    CheckInfo(
        "rule.instance-type",
        "a pinned type agrees with x-oold-instance-rdf-type",
        rule="OOLD-INS-002",
        per_version=True,
        run=_inline_type_disagrees,
    ),
    CheckInfo(
        "rule.free-text-iri",
        "a free-text range is not coerced to @id",
        rule="OOLD-INS-009",
        per_version=True,
        run=_free_text_range_coerced_to_iri,
    ),
    CheckInfo(
        "rule.closed-object",
        "a closed object still permits $schema and @context",
        rule="OOLD-INS-005",
        per_version=True,
        run=_closed_object_rejects_metadata,
    ),
    CheckInfo(
        "rule.version",
        "a schema states x-oold-version",
        rule="OOLD-VER-002",
        per_version=True,
        run=_missing_version,
    ),
    CheckInfo(
        "rule.id-alias",
        "@id is exposed through an alias",
        rule="OOLD-INS-007",
        per_version=True,
        run=_id_not_aliased,
    ),
    CheckInfo(
        "rule.dialect",
        "a schema declares the OO-LD dialect",
        rule="OOLD-EXT-002",
        per_version=True,
        run=_dialect_not_declared,
    ),
    CheckInfo(
        "rule.processing-mode",
        "a context declares @version 1.1",
        rule="OOLD-EXT-001",
        per_version=True,
        run=_processing_mode_not_declared,
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

    This is the one place the presence/deprecation gating lives, shared by the ten self-contained
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
) -> list[RuleFinding]:
    """Apply the rule checks that the selected specification version actually states.

    ``catalog`` maps rule id to its catalogue entry for the meta version in use. When given, a
    check whose rule is absent from it is **skipped**: that version never stated the requirement,
    and enforcing it would report a violation of something the target does not require. A
    deprecated rule is skipped for the same reason from the other end. See :func:`catalog_gate`.

    When ``catalog`` is None the version ships no catalogue at all, and every one of these ten
    checks skips: none of them predates the catalogue (:attr:`CheckInfo.predates_catalog` is
    False for all of them), so there is nothing pre-catalogue evidence could attribute the rule
    to.
    """
    findings: list[RuleFinding] = []
    for check in (c for c in CHECKS if c.run):
        gate = catalog_gate(check, catalog)
        if gate is not None:
            findings.append(gate)
            continue
        rule = (catalog or {}).get(check.rule)
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
