"""Orchestration: run the checks over targets, across meta-schema versions.

The one structural decision worth knowing: only two checks depend on which meta-schema version
is in use (``schema.meta`` and ``lint.pattern``). Everything else - ``$ref`` resolution,
generation, RDF round-trip, predicate attribution - is version independent. So the version
independent work runs *once* and only the two dependent checks fan out across the selected
versions. With ``--meta all`` that is the difference between linear and near-constant cost.

Check ids are stable and dotted, so results can be filtered, compared across runs, and lined up
against the reference harness's sections. See ``docs/how-to/validation.md``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .check_registry import ContextView, rule_map, run_rule_checks
from .check_registry import rule_for as _rule_for_check
from .compliance import run_suite, vocabulary_coverage
from .context_graph import cyclic_scoped_contexts
from .context_resolution import find_alias_keys, resolve_context
from .formats import OOLD_FORMAT_CHECKER
from .frame import collect_composed_properties
from .generate import MAX_VARIANTS, collect_variants, generate
from .instance_checks import roundtrip_instance
from .instance_checks import validate_instance as _validate_instance_doc
from .loader import DocumentLoader
from .meta_store import MetaBundle, MetaSchemaError, resolve_selection
from .pattern_lint import lint
from .predicates import check_predicates
from .report import FAIL, OK, SKIP, WARN, Report
from .resolve import Resolver, SchemaResolutionError, bound_schema
from .roundtrip import roundtrip
from .schema_checks import check_usable_as_validator, validate_against_meta

SCHEMA_SUFFIX = ".schema.json"
INSTANCE_SUFFIX = ".instance.json"

#: Why a schema's JSON-LD checks were skipped. Shared so the message is identical everywhere.
CYCLIC_NOTE = (
    "reaches a cyclic scoped @context, which neither PyLD nor jsonld.js can process "
    "(flatten it to the top-level context)"
)


@dataclass
class Options:
    """Everything that varies between runs."""

    meta: tuple[str, ...] = ("latest",)
    offline: bool = False
    max_variants: int = MAX_VARIANTS
    only: tuple[str, ...] = ()
    skip: tuple[str, ...] = ()
    cache_dir: Path | None = None

    def wants(self, check_id: str) -> bool:
        if self.only and not any(check_id.startswith(prefix) for prefix in self.only):
            return False
        return not any(check_id.startswith(prefix) for prefix in self.skip)


@dataclass
class _Run:
    """Mutable state shared by the checks of one run."""

    options: Options
    report: Report
    resolver: Resolver
    loader: DocumentLoader
    bundles: list[MetaBundle]
    directory: Path
    schemas: dict[str, Any] = field(default_factory=dict)
    cyclic: set[str] = field(default_factory=set)
    _bounded: dict[str, Any] = field(default_factory=dict)

    def bounded(self, name: str) -> dict[str, Any]:
        """Dereference and bound a schema by file name, memoised for the run."""
        if name not in self._bounded:
            resolved = self.resolver.load(self.directory / name)
            schema = bound_schema(self.resolver.dereference(resolved).schema)
            schema.pop("$schema", None)
            self._bounded[name] = schema
        return self._bounded[name]

    def add(self, check_id: str, *args: Any, **kwargs: Any) -> None:
        """Record a check, tagging it with the rule it enforces where one is known.

        The rule is attached here rather than at each call site so the mapping stays in one
        place, and it is only attached when the meta version in use actually ships a catalog
        containing that id - an older version reports findings with no citation.
        """
        if not self.options.wants(check_id):
            return
        kwargs.setdefault("rule", self.rule_for(check_id))
        self.report.add(check_id, *args, **kwargs)

    def rule_for(self, check_id: str) -> str | None:
        rule_id = _rule_for_check(check_id)
        if not rule_id:
            return None
        return rule_id if any(b.rule(rule_id) for b in self.bundles) else None


# ---------------------------------------------------------------------------- setup


def _start(source: Path, options: Options, label: str) -> _Run:
    resolver = Resolver(offline=options.offline, cache_dir=options.cache_dir)
    directory = source if source.is_dir() else source.parent
    report = Report(source=str(source))
    bundles = resolve_selection(options.meta, offline=options.offline)
    report.meta_versions = [b.version for b in bundles]

    run = _Run(
        options=options,
        report=report,
        resolver=resolver,
        loader=DocumentLoader(resolver, directory=directory),
        bundles=bundles,
        directory=directory,
    )

    for bundle in bundles:
        problems = bundle.self_check()
        if problems:
            run.add(
                "meta.self-check",
                f"meta-schema {bundle.version}",
                FAIL,
                "; ".join(problems),
                {"origin": bundle.origin},
                bundle.version,
            )
    report.notes.append(f"target: {label}")
    return run


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------- schema checks


def _check_schema(run: _Run, name: str) -> None:
    """Every check that applies to one schema file."""
    try:
        raw = run.schemas[name]
    except KeyError:  # pragma: no cover - callers populate schemas first
        return

    # -- meta-schema well-formedness (per version) ---------------------------------
    for bundle in run.bundles:
        result = validate_against_meta(raw, bundle)
        problems = list(result.errors) + check_usable_as_validator(raw)
        if problems:
            extra = f" (+{result.truncated} more)" if result.truncated else ""
            run.add(
                "schema.meta",
                name,
                FAIL,
                problems[0] + extra,
                {"errors": problems},
                bundle.version,
            )
        else:
            run.add("schema.meta", name, OK, meta_version=bundle.version)

    # -- $ref composition (version independent) ------------------------------------
    try:
        resolved = run.resolver.load(run.directory / name)
        deref = run.resolver.dereference(resolved)
    except SchemaResolutionError as exc:
        run.add("schema.refs", name, FAIL, str(exc))
        return

    if deref.unresolved:
        run.add("schema.refs", name, FAIL, deref.unresolved[0], {"unresolved": deref.unresolved})
        return
    run.add("schema.refs", name, OK, "", {"resolved": len(deref.resolved_refs)})

    # -- pattern lint --------------------------------------------------------------
    first = None
    for bundle in run.bundles:
        result = lint(raw, bundle)
        first = first or result
        if result.schema_errors:
            run.add(
                "lint.pattern",
                name,
                FAIL,
                result.schema_errors[0],
                {"errors": result.schema_errors},
                bundle.version,
            )
        else:
            run.add("lint.pattern", name, OK, meta_version=bundle.version)

    if first is not None:
        # These two correlate `properties` with `@context`, so no meta-schema version can
        # express them and they are reported once rather than per version.
        if first.missing_container:
            joined = ", ".join(first.missing_container)
            plural = "ies" if len(first.missing_container) > 1 else "y"
            run.add(
                "lint.container",
                name,
                FAIL,
                f"strict array propert{plural} without @container @set/@list: {joined}",
                {"properties": first.missing_container},
            )
        else:
            run.add("lint.container", name, OK)

        if first.missing_iri_format:
            joined = ", ".join(first.missing_iri_format)
            plural = "ies" if len(first.missing_iri_format) > 1 else "y"
            run.add(
                "lint.iri-format",
                name,
                WARN,
                f"IRI reference propert{plural} without an iri-reference/uri* format: {joined}",
                {"properties": first.missing_iri_format},
            )

    _check_schema_jsonld(run, name, raw)


def _check_schema_jsonld(run: _Run, name: str, raw: dict[str, Any]) -> None:
    """Generation, round-trip, remote-context and attribution for one schema."""
    from pyld import jsonld

    schema = run.bounded(name)

    # -- satisfiability ------------------------------------------------------------
    generated = generate(schema)
    if not generated.ok:
        run.add("generate.satisfiable", name, FAIL, generated.error or "generation failed")
        return

    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(schema, format_checker=OOLD_FORMAT_CHECKER)
    errors = sorted(validator.iter_errors(generated.instance), key=lambda e: list(e.absolute_path))
    if errors:
        run.add(
            "generate.satisfiable",
            name,
            FAIL,
            f"generated instance is rejected by its own schema: {errors[0].message}",
            {"sample": generated.instance},
        )
        return
    run.add("generate.satisfiable", name, OK, "", {"notes": generated.notes})

    cyclic = name in run.cyclic
    context_url = run.loader.url_for(name)

    # -- generated-instance round-trip ---------------------------------------------
    if cyclic:
        run.add("roundtrip.generated", name, SKIP, CYCLIC_NOTE)
    else:
        result = roundtrip(schema, generated.instance, context_url, run.loader)
        if result.error:
            run.add("roundtrip.generated", name, FAIL, result.error)
        elif result.lost:
            joined = ", ".join(result.lost)
            plural = "ies" if len(result.lost) > 1 else "y"
            run.add(
                "roundtrip.generated",
                name,
                FAIL,
                f"propert{plural} lost through RDF (unmapped in @context?): {joined}",
                {"lost": result.lost},
            )
        else:
            re_errors = sorted(validator.iter_errors(result.restored), key=lambda e: list(e.absolute_path))
            if re_errors:
                run.add(
                    "roundtrip.generated",
                    name,
                    FAIL,
                    "reconstruction fails its schema (shape not preserved by @context?): " + re_errors[0].message,
                    {"restored": result.restored},
                )
            else:
                run.add(
                    "roundtrip.generated",
                    name,
                    OK,
                    "",
                    {"triples": result.triples, "method": result.method},
                )

    # -- schema usable as a remote context -----------------------------------------
    if cyclic:
        run.add("context.remote", name, SKIP, CYCLIC_NOTE)
    else:
        try:
            jsonld.expand(
                {"@context": context_url, "@id": "https://example.org/dummy"},
                run.loader.options(base=run.loader.base_url),
            )
            run.add("context.remote", name, OK)
        except Exception as exc:
            from .loader import describe_jsonld_error

            run.add("context.remote", name, FAIL, describe_jsonld_error(exc))

    _check_predicates(run, name, raw, schema, generated.instance)

    # -- per-branch variant coverage -----------------------------------------------
    if cyclic:
        return
    variants, total = collect_variants(schema, limit=run.options.max_variants)
    if total > len(variants):
        run.report.notes.append(f"{name}: {total} oneOf/anyOf branches, checking the first {len(variants)}")
    for variant in variants:
        _check_variant(run, name, schema, variant, validator, context_url)


def _check_variant(run: _Run, name: str, schema, variant, validator, context_url: str) -> None:
    label = f"{name} {variant.label}"
    produced = generate(variant.schema)
    if not produced.ok:
        run.add("variants", label, FAIL, produced.error or "generation failed")
        return
    errors = sorted(validator.iter_errors(produced.instance), key=lambda e: list(e.absolute_path))
    if errors:
        run.add("variants", label, FAIL, f"generated instance rejected: {errors[0].message}")
        return
    result = roundtrip(schema, produced.instance, context_url, run.loader)
    if result.error:
        run.add("variants", label, FAIL, result.error)
    elif result.lost:
        run.add(
            "variants",
            label,
            FAIL,
            f"properties lost through RDF: {', '.join(result.lost)}",
            {"lost": result.lost},
        )
    else:
        re_errors = sorted(validator.iter_errors(result.restored), key=lambda e: list(e.absolute_path))
        if re_errors:
            run.add("variants", label, FAIL, f"reconstruction fails its schema: {re_errors[0].message}")
        else:
            run.add("variants", label, OK)


def _check_predicates(run: _Run, name: str, raw, schema, sample) -> None:
    """Attribute each declared property to the predicate it produces."""
    if not run.options.wants("context.predicates") or not isinstance(sample, dict):
        return
    try:
        resolved = run.resolver.load(run.directory / name)
        context = resolve_context(raw, resolved.base_uri, run.resolver)
    except SchemaResolutionError as exc:
        run.add("context.predicates", name, FAIL, str(exc))
        return

    if context.errors:
        run.add("context.predicates", name, FAIL, context.errors[0], {"errors": context.errors})
        return
    if context.is_empty:
        run.add("context.predicates", name, SKIP, "schema declares no @context")
        return

    _run_rule_checks(run, name, raw, ContextView(terms=context.terms(), entries=list(context.context)))

    id_key, type_key = find_alias_keys(context.terms())
    declared = set(collect_composed_properties(schema)) | {id_key, type_key}
    result = check_predicates(sample, context.as_jsonld(), declared_properties=declared)

    if result.suspicious:
        first = next(iter(result.suspicious.items()))
        run.add(
            "context.predicates",
            name,
            FAIL,
            f"property {first[0]!r} expands to {first[1]!r}, which is not an absolute IRI: "
            "the prefix is probably undefined",
            result.to_dict(include_documents=True),
        )
    elif result.dropped:
        run.add(
            "context.predicates",
            name,
            FAIL,
            f"propert{'ies' if len(result.dropped) > 1 else 'y'} with no @context term: " + ", ".join(result.dropped),
            result.to_dict(include_documents=True),
        )
    else:
        run.add(
            "context.predicates",
            name,
            OK,
            "",
            {"mapped": len(result.mapped), "aliased": len(result.aliased)},
        )


# ---------------------------------------------------------------------------- instances


def _run_rule_checks(run: _Run, name: str, raw: dict[str, Any], context: ContextView) -> None:
    """Report the narrow, single-rule checks for one schema, per meta-schema version.

    These are the only checks whose *applicability* depends on the version: each enforces one
    statement, and a version that never stated it must not be judged against it. So they run once
    per selected version, driven by that version's catalogue - which also supplies the severity,
    so a MUST relaxed to a SHOULD upstream changes the outcome with no code change here.

    A version shipping no catalogue skips them entirely rather than guessing. Running blind would
    assert requirements that version may never have stated, which is the same false-positive class
    as judging a schema on its literal rather than resolved `@context`.

    A passing check is still recorded, so `--verbose` shows what was verified and the counts line
    up with what `oold rules list` claims is enforced.
    """
    for bundle in run.bundles:
        if not bundle.has_rules:
            run.add(
                "rule.checks",
                name,
                SKIP,
                f"meta-schema {bundle.version} ships no rule catalogue, so per-rule checks "
                "cannot be attributed to a stated requirement",
                meta_version=bundle.version,
            )
            continue
        catalog = {r["id"]: r for r in bundle.rules}
        for finding in run_rule_checks(raw, context, catalog):
            run.add(
                finding.check_id,
                name,
                finding.status,
                finding.message,
                finding.detail,
                bundle.version,
            )


def _check_instance_file(run: _Run, name: str, instance: Any = None) -> None:
    """Validate and round-trip one instance.

    ``instance`` may be supplied already parsed, which is how an explicit ``--schema`` override
    is applied: the override rewrites ``$schema`` in memory so this single path still handles it.
    """
    if instance is None:
        try:
            instance = _read(run.directory / name)
        except (OSError, json.JSONDecodeError) as exc:
            run.add("instance.schema", name, FAIL, f"could not be read: {exc}")
            return

    schema_ref = instance.get("$schema") if isinstance(instance, dict) else None
    if not schema_ref:
        run.add("instance.schema", name, FAIL, "instance names no schema ($schema is missing)")
        return

    try:
        schema = run.bounded(schema_ref)
    except SchemaResolutionError as exc:
        run.add("instance.schema", name, FAIL, f"schema {schema_ref!r} could not be loaded: {exc}")
        return

    result = _validate_instance_doc(instance, schema)
    if result.valid:
        run.add("instance.schema", name, OK, f"instance of {schema_ref}")
    else:
        run.add("instance.schema", name, FAIL, result.errors[0], {"errors": result.errors})

    if schema_ref in run.cyclic:
        run.add("roundtrip.instance", name, SKIP, f"its schema {CYCLIC_NOTE}")
        return

    rt = roundtrip_instance(instance, schema, run.loader, run.loader.url_for(name), run.loader.url_for(schema_ref))
    if rt.error:
        run.add("roundtrip.instance", name, FAIL, rt.error)
    elif not rt.lossless:
        run.add(
            "roundtrip.instance",
            name,
            FAIL,
            "instance != roundtrip (incomplete @context?)",
            {"in": rt.original_canonical, "out": rt.restored_canonical},
        )
    else:
        run.add(
            "roundtrip.instance",
            name,
            OK,
            f"{rt.triples} triples, lossless ({rt.method})",
            {"triples": rt.triples, "method": rt.method},
        )


# ---------------------------------------------------------------------------- entry points


def _collect(run: _Run, schema_names: list[str]) -> None:
    for name in schema_names:
        try:
            run.schemas[name] = _read(run.directory / name)
        except (OSError, json.JSONDecodeError) as exc:
            run.add("schema.meta", name, FAIL, f"could not be read: {exc}")
    run.cyclic = cyclic_scoped_contexts(run.schemas)


def validate_directory(path: str | Path, options: Options | None = None) -> Report:
    """Validate every schema and instance in a directory, the general-workflow tier."""
    options = options or Options()
    directory = Path(path)
    if not directory.is_dir():
        report = Report(source=str(directory))
        report.fatal_error = f"not a directory: {directory}"
        return report

    try:
        run = _start(directory, options, f"directory {directory}")
    except MetaSchemaError as exc:
        report = Report(source=str(directory))
        report.fatal_error = str(exc)
        return report

    schema_names = sorted(p.name for p in directory.glob(f"*{SCHEMA_SUFFIX}"))
    instance_names = sorted(p.name for p in directory.glob(f"*{INSTANCE_SUFFIX}"))
    if not schema_names and not instance_names:
        run.report.fatal_error = f"no *{SCHEMA_SUFFIX} or *{INSTANCE_SUFFIX} files in {directory}"
        return run.report

    _collect(run, schema_names)
    for name in schema_names:
        _check_schema(run, name)
    for name in instance_names:
        _check_instance_file(run, name)
    return run.report


def validate_schema(source: str | Path, options: Options | None = None) -> Report:
    """Validate a single schema file.

    Sibling schemas in the same directory are still read, because the cyclic-context detection
    is a property of the reference *graph* rather than of one document.
    """
    options = options or Options()
    path = Path(source)
    if path.is_dir():
        return validate_directory(path, options)
    if not path.is_file():
        report = Report(source=str(path))
        report.fatal_error = f"schema file not found: {path}"
        return report

    try:
        run = _start(path, options, f"schema {path.name}")
    except MetaSchemaError as exc:
        report = Report(source=str(path))
        report.fatal_error = str(exc)
        return report

    _collect(run, sorted(p.name for p in run.directory.glob(f"*{SCHEMA_SUFFIX}")))
    if path.name not in run.schemas:
        try:
            run.schemas[path.name] = _read(path)
        except (OSError, json.JSONDecodeError) as exc:
            run.report.fatal_error = f"{path.name} could not be read: {exc}"
            return run.report
    _check_schema(run, path.name)
    return run.report


def validate_instance(source: str | Path, schema: str | Path | None = None, options: Options | None = None) -> Report:
    """Validate one instance document against the schema it names, or an explicit one."""
    options = options or Options()
    path = Path(source)
    if not path.is_file():
        report = Report(source=str(path))
        report.fatal_error = f"instance file not found: {path}"
        return report

    try:
        run = _start(path, options, f"instance {path.name}")
    except MetaSchemaError as exc:
        report = Report(source=str(path))
        report.fatal_error = str(exc)
        return report

    if schema is not None:
        # An explicit schema overrides $schema; rewrite it so one code path handles both.
        try:
            instance = _read(path)
        except (OSError, json.JSONDecodeError) as exc:
            run.report.fatal_error = f"{path.name} could not be read: {exc}"
            return run.report
        schema_path = Path(schema)
        if schema_path.parent.resolve() != run.directory.resolve():
            run.report.fatal_error = (
                "an explicit --schema must sit in the same directory as the instance, so "
                f"relative @context references resolve ({schema_path.parent} != {run.directory})"
            )
            return run.report
        instance["$schema"] = schema_path.name
        run.report.notes.append(f"schema overridden with {schema_path.name}")
        _collect(run, sorted(p.name for p in run.directory.glob(f"*{SCHEMA_SUFFIX}")))
        _check_instance_file(run, path.name, instance)
        return run.report

    _collect(run, sorted(p.name for p in run.directory.glob(f"*{SCHEMA_SUFFIX}")))
    _check_instance_file(run, path.name)
    return run.report


def run_compliance(path: str | Path, options: Options | None = None) -> Report:
    """Run a compliance suite directory, plus the vocabulary-coverage cross-check."""
    options = options or Options()
    directory = Path(path)
    report = Report(source=str(directory))
    if not directory.is_dir():
        report.fatal_error = f"not a directory: {directory}"
        return report

    # Fixtures reference example schemas by name, and those live one level up.
    schema_dir = directory.parent
    try:
        run = _start(schema_dir, options, f"compliance suite {directory}")
    except MetaSchemaError as exc:
        report.fatal_error = str(exc)
        return report
    run.report.source = str(directory)

    for bundle in run.bundles:
        result = run_suite(directory, bundle, run.loader, dereference=run.bounded)
        for error in result.errors:
            run.add("compliance.suite", directory.name, FAIL, error, meta_version=bundle.version)
        for case in result.cases:
            target = f"{case.file} :: {case.description}"
            run.add(
                f"compliance.{case.kind}",
                target,
                OK if case.passed else FAIL,
                case.detail,
                {"group": case.group},
                bundle.version,
            )
        uncovered = vocabulary_coverage(bundle, result.covered_keywords)
        if uncovered:
            run.add(
                "coverage.vocab",
                directory.name,
                FAIL,
                f"{len(uncovered)} keyword(s) defined in the meta-schemas but not tested: " + ", ".join(uncovered),
                {"uncovered": uncovered},
                bundle.version,
            )
        else:
            run.add(
                "coverage.vocab",
                directory.name,
                OK,
                f"all {len(bundle.declared_keywords())} keywords covered",
                meta_version=bundle.version,
            )
        _check_rule_coverage(run, directory.name, bundle)
    return run.report


def _check_rule_coverage(run: _Run, target: str, bundle: MetaBundle) -> None:
    """Report which checkable rules this validator actually enforces.

    Both directions are reported as a warning rather than a failure, for different reasons.

    An unenforced checkable rule is the gap the catalog exists to expose; failing on it would
    block every run on requirements nobody has implemented a check for yet.

    A mapped id the catalog does not contain looks like a dangling reference, but it is
    ambiguous: it is equally what a *older* meta version looks like, one minted before that rule
    existed. Failing would make validating against an older version break for no reason. A
    genuine typo in the registry is caught instead by the shape test and by the live parity test
    that resolves every mapping against the current upstream catalog.
    """
    if not bundle.has_rules:
        run.add(
            "coverage.rules",
            target,
            SKIP,
            f"meta-schema {bundle.version} ships no rule catalog",
            meta_version=bundle.version,
        )
        return

    mapped = set(rule_map().values())
    unknown = sorted({r for r in mapped if not bundle.rule(r)})
    checkable = bundle.checkable_rules()
    missing = sorted(r["id"] for r in checkable if r["id"] not in mapped)

    notes: list[str] = []
    if missing:
        notes.append(f"{len(missing)}/{len(checkable)} checkable rule(s) have no check: " + ", ".join(missing))
    if unknown:
        notes.append(
            f"{len(unknown)} mapped rule id(s) absent from this catalog (newer than "
            f"{bundle.version}, or renamed): " + ", ".join(unknown)
        )

    if notes:
        run.add(
            "coverage.rules",
            target,
            WARN,
            "; ".join(notes),
            {"unenforced": missing, "unknown": unknown},
            bundle.version,
        )
    else:
        run.add(
            "coverage.rules",
            target,
            OK,
            f"all {len(checkable)} checkable rules are enforced",
            meta_version=bundle.version,
        )
