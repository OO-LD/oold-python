"""MCP server exposing OO-LD validation as tools.

A thin wrapper: every tool delegates to the same pipeline the CLI uses, so there is no second
copy of the validation logic to keep in sync.

Two conventions hold throughout.

* Errors come back as data, never as exceptions. A caller asking about a broken schema wants the
  report explaining why it is broken, which is precisely the case where raising would destroy
  the answer.
* ``verbosity`` is ``"summary"`` by default. ``"full"`` adds per-check detail, generated
  instances and reconstructed documents, which is verbose enough to be worth opting into.

Run with ``python -m oold.validation.mcp_server``; transport is stdio.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

try:
    # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # pragma: no cover - depends on the installed mcp major version
    # mcp 1.x, where the same class is called FastMCP. The parts used here - the `tool`
    # decorator and `run(transport=...)` - are identical across both.
    from mcp.server.fastmcp import FastMCP as _Server  # ty: ignore[unresolved-import]

from .cli import SPEC_RULE_URL
from .generate import generate
from .meta_store import MetaSchemaError, Rule, describe_store, resolve_selection
from .pipeline import Options, run_compliance, validate_directory, validate_instance, validate_schema
from .predicates import check_predicates
from .report import Report, failure_reasons
from .resolve import Resolver, SchemaResolutionError, bound_schema

mcp = _Server("oold-validation")

Verbosity = Literal["summary", "full"]


def _options(meta: list[str] | None, offline: bool) -> Options:
    return Options(meta=tuple(meta) if meta else ("latest",), offline=offline)


# ---------------------------------------------------------------------------- result models
#
# Every tool below returns one of these rather than a bare dict, so an MCP client gets a real
# result schema instead of an opaque `dict[str, Any]`. See docs/architecture.md, "pydantic at
# the boundaries", for why this package draws the line here and not around every internal value.


class CheckResult(BaseModel):
    """One check's outcome for one target, mirroring :meth:`report.Check.to_dict`."""

    id: str = Field(description="The check id, e.g. lint.container or rule.id-fragment.")
    target: str = Field(description="What was checked: a schema file, an instance, or a directory entry.")
    status: str = Field(description="ok, fail, warn, or skip.")
    message: str = Field(default="", description="Why the check produced this status, when it is not ok.")
    detail: dict[str, Any] | None = Field(
        default=None, description="Extra structured detail behind the message. Only present with verbosity='full'."
    )
    meta_version: str | None = Field(
        default=None, description="The meta-schema version this check ran against, for version-dependent checks."
    )
    rule: str | None = Field(
        default=None, description="The specification rule id this check enforces, e.g. OOLD-RT-08f2, if any."
    )


class ReportSummary(BaseModel):
    """Counts and verdict for a run, mirroring :meth:`report.Report.summary`."""

    source: str = Field(description="What was validated.")
    passed: bool = Field(description="True only when no check failed.")
    meta_versions: list[str] = Field(default_factory=list, description="The meta-schema versions validated against.")
    targets: int = Field(description="How many distinct schemas/instances were checked.")
    checks: int = Field(description="How many checks ran in total.")
    ok: int = Field(description="How many checks passed.")
    fail: int = Field(description="How many checks failed.")
    warn: int = Field(description="How many checks warned.")
    skip: int = Field(description="How many checks were skipped; each skipped check's message says why.")
    fatal_error: str | None = Field(default=None, description="Set only when the run could not start at all.")


class ValidationResult(BaseModel):
    """The outcome of validating a schema, an instance, a directory, or running the compliance suite.

    Mirrors :meth:`report.Report.to_dict` plus ``problems``, a flattened list of failure reasons.
    The fields that matter most are ``summary`` (counts and the verdict) and ``problems``.
    """

    source: str | None = Field(default=None, description="What was validated.")
    passed: bool = Field(description="True only when no check failed and no fatal error occurred.")
    summary: ReportSummary | None = Field(default=None, description="Counts and verdict for the run.")
    checks: list[CheckResult] = Field(default_factory=list, description="Every check that ran.")
    notes: list[str] = Field(default_factory=list, description="Free-form notes about the run.")
    fatal_error: str | None = Field(
        default=None, description="Set instead of running any checks when the run could not start at all."
    )
    problems: list[str] = Field(default_factory=list, description="Each failure reason, in readable form.")


def _payload(report: Report, verbosity: Verbosity) -> ValidationResult:
    payload = report.to_dict(verbosity)
    payload["problems"] = failure_reasons(report)
    return ValidationResult.model_validate(payload)


def _materialise(
    source: str, suffix: str, directory: Path | None = None
) -> tuple[Path, tempfile.TemporaryDirectory | None]:
    """Turn a path or a raw JSON string into a file on disk.

    The checks are directory-relative by nature: a schema's ``@context`` and ``$ref`` entries are
    usually relative siblings. A schema passed as raw JSON therefore has to be written somewhere
    before it can be validated, and it will only resolve if it has no relative references.

    Pass ``directory`` to materialise into a directory an earlier call already created - an
    instance and an inline schema, for example, must land side by side so the instance's
    ``$schema`` reference to it resolves. The directory's cleanup remains the caller's
    responsibility; no ``TemporaryDirectory`` is returned when one is supplied.
    """
    text = source.strip()
    if not text.startswith("{"):
        return Path(source), None

    holder: tempfile.TemporaryDirectory | None = None
    if directory is None:
        holder = tempfile.TemporaryDirectory(prefix="oold-validation-")
        directory = Path(holder.name)
    name = "Inline" + suffix
    target = directory / name
    target.write_text(text, encoding="utf-8")
    return target, holder


@mcp.tool()
def validate_oold_schema(
    schema: str,
    meta: list[str] | None = None,
    offline: bool = False,
    verbosity: Verbosity = "summary",
) -> ValidationResult:
    """Run the full OO-LD pipeline over one schema.

    Checks the schema against the OO-LD meta-schema, resolves its $ref composition, lints its
    @context for round-trip-safe patterns, generates an instance and confirms it validates, then
    round-trips that instance through RDF to prove no property is silently lost.

    Args:
        schema: Path to a *.schema.json file, or the schema itself as a JSON string. A path is
            strongly preferred: relative @context and $ref entries only resolve on disk.
        meta: Meta-schema versions, e.g. ["latest"], ["0.7.0"], ["remote"], ["all"]. Several may
            be given to validate against all of them at once.
        offline: Never fetch over the network; use local files and the cache only.
        verbosity: "full" adds per-check detail and generated documents.
    """
    path, holder = _materialise(schema, ".schema.json")
    try:
        return _payload(validate_schema(path, _options(meta, offline)), verbosity)
    except MetaSchemaError as exc:
        return ValidationResult(passed=False, fatal_error=str(exc))
    finally:
        if holder:
            holder.cleanup()


@mcp.tool()
def validate_oold_instance(
    instance: str,
    schema: str | None = None,
    meta: list[str] | None = None,
    offline: bool = False,
    verbosity: Verbosity = "summary",
) -> ValidationResult:
    """Check whether a specific document conforms to an OO-LD schema.

    Validates the instance structurally against its schema, with formats asserted, then projects
    it to RDF and back to confirm the reconstruction is identical. This answers "does this
    document conform", as opposed to "is this schema sound".

    Args:
        instance: Path to the instance document, or the instance itself as a JSON string. It
            names its schema with $schema; relative @context references only resolve for a
            document on disk with its siblings.
        schema: Optional path to a schema, or the schema itself as a JSON string, overriding
            $schema. Must sit in the same directory as the instance so relative @context
            references resolve; when both are given as raw JSON, they are materialised into the
            same temporary directory so this holds automatically.
        meta: Meta-schema versions, as in validate_oold_schema.
        offline: Never fetch over the network.
        verbosity: "full" adds the canonical forms of both sides of the round-trip.
    """
    instance_path, instance_holder = _materialise(instance, ".instance.json")
    schema_path = None
    schema_holder = None
    try:
        if schema is not None:
            shared_dir = Path(instance_holder.name) if instance_holder else None
            schema_path, schema_holder = _materialise(schema, ".schema.json", shared_dir)
        report = validate_instance(instance_path, schema_path, _options(meta, offline))
        return _payload(report, verbosity)
    except MetaSchemaError as exc:
        return ValidationResult(passed=False, fatal_error=str(exc))
    finally:
        if schema_holder:
            schema_holder.cleanup()
        if instance_holder:
            instance_holder.cleanup()


@mcp.tool()
def validate_oold_directory(
    directory: str,
    meta: list[str] | None = None,
    offline: bool = False,
    verbosity: Verbosity = "summary",
) -> ValidationResult:
    """Validate every *.schema.json and *.instance.json in a directory.

    Runs the same general-workflow checks as validating a single schema, over every schema and
    instance the directory contains, so a downstream repository can conformance-check its
    generated schemas.

    Args:
        directory: The directory to validate.
        meta: Meta-schema versions, as in validate_oold_schema.
        offline: Never fetch over the network.
        verbosity: "full" adds per-check detail.
    """
    try:
        report = validate_directory(Path(directory), _options(meta, offline))
    except MetaSchemaError as exc:
        return ValidationResult(passed=False, fatal_error=str(exc))
    return _payload(report, verbosity)


@mcp.tool()
def run_oold_compliance(
    directory: str,
    meta: list[str] | None = None,
    offline: bool = False,
    verbosity: Verbosity = "summary",
) -> ValidationResult:
    """Run a deterministic compliance suite and the vocabulary-coverage cross-check.

    Args:
        directory: Directory of fixture files, for example oold-schema's examples/compliance.
        meta: Meta-schema versions, as in validate_oold_schema.
        offline: Never fetch over the network.
        verbosity: "full" lists every case rather than only the failures.
    """
    try:
        report = run_compliance(Path(directory), _options(meta, offline))
    except MetaSchemaError as exc:
        return ValidationResult(passed=False, fatal_error=str(exc))
    return _payload(report, verbosity)


class GenerateInstanceResult(BaseModel):
    """The result of generating a deterministic example instance from a schema."""

    ok: bool = Field(description="True when generation succeeded and the instance validates against its schema.")
    instance: Any = Field(default=None, description="The generated instance document, or None on failure.")
    notes: list[str] = Field(default_factory=list, description="Notes about how the instance was built.")
    error: str | None = Field(default=None, description="Why generation failed, when ok is False.")
    unresolved_refs: list[str] = Field(
        default_factory=list, description="$ref targets that could not be resolved while dereferencing the schema."
    )


@mcp.tool()
def generate_oold_instance(schema: str, offline: bool = False) -> GenerateInstanceResult:
    """Generate a deterministic example instance from a schema.

    Every declared property is populated, including those inherited through allOf, and declared
    formats are respected. Useful on its own for seeing what a schema actually covers.

    Args:
        schema: Path to a *.schema.json file, or the schema itself as a JSON string.
        offline: Never fetch over the network while resolving $refs.
    """
    path, holder = _materialise(schema, ".schema.json")
    try:
        resolver = Resolver(offline=offline)
        loaded = resolver.load(path)
        deref = resolver.dereference(loaded)
        bounded = bound_schema(deref.schema)
        bounded.pop("$schema", None)
        result = generate(bounded)
    except SchemaResolutionError as exc:
        return GenerateInstanceResult(ok=False, instance=None, error=str(exc))
    finally:
        if holder:
            holder.cleanup()

    return GenerateInstanceResult(
        ok=result.ok,
        instance=result.instance,
        notes=result.notes,
        error=result.error,
        unresolved_refs=deref.unresolved,
    )


class PropertyOutcomeResult(BaseModel):
    """What happened to one instance property when the document was expanded."""

    name: str = Field(description="The property key in the instance document.")
    status: str = Field(description="mapped, alias, dropped, or suspicious.")
    predicate: str | None = Field(default=None, description="The RDF predicate the property expanded to, if any.")
    detail: str | None = Field(default=None, description="Why the property was classified this way.")


class ContextMappingResult(BaseModel):
    """Which properties of a JSON-LD document carry meaning, and which do not.

    Two failure modes are distinguished: a property that expands to nothing (``dropped``, it has
    no @context term) and one that expands to a non-absolute IRI (``suspicious``, its prefix is
    probably undefined). The second is the dangerous one, because the document looks fine and
    round-trips cleanly while pointing at a meaningless predicate.
    """

    ok: bool = Field(description="True when every checked property mapped or aliased cleanly.")
    dropped: list[str] = Field(default_factory=list, description="Properties with no @context term at all.")
    suspicious: dict[str, str] = Field(
        default_factory=dict, description="Property name -> predicate, for properties expanding to a non-absolute IRI."
    )
    mapped_count: int | None = Field(default=None, description="How many properties mapped to a grounded predicate.")
    aliased: dict[str, str] = Field(
        default_factory=dict, description="Property name -> JSON-LD alias it maps to, e.g. @id."
    )
    undeclared: list[str] = Field(
        default_factory=list, description="Properties outside the schema's declared set, so left unchecked."
    )
    errors: list[str] = Field(default_factory=list, description="Errors encountered while reading or expanding.")
    outcomes: list[PropertyOutcomeResult] = Field(
        default_factory=list, description="Per-property detail behind the summary fields above."
    )
    mapped: dict[str, str] = Field(
        default_factory=dict, description="Property name -> predicate, for cleanly mapped properties."
    )


@mcp.tool()
def check_context_mapping(document: str, context: str | None = None) -> ContextMappingResult:
    """Report which properties of a JSON-LD document carry meaning, and which do not.

    No schema and no generation involved.

    Args:
        document: The JSON-LD document. A path or raw JSON is accepted.
        context: Optional context, overriding the document's own @context. A path or raw JSON
            (object or array) is accepted; anything else is used as the context value itself,
            e.g. a remote context IRI.
    """
    doc_path, doc_holder = _materialise(document, ".document.json")
    try:
        try:
            parsed = json.loads(doc_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return ContextMappingResult(ok=False, errors=[f"could not read the document: {exc}"])

        active = parsed.get("@context")
        if context is not None:
            text = context.strip()
            if text.startswith(("{", "[")):
                try:
                    active = json.loads(text)
                except json.JSONDecodeError as exc:
                    return ContextMappingResult(ok=False, errors=[f"context is not valid JSON: {exc}"])
            elif Path(context).is_file():
                try:
                    active = json.loads(Path(context).read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    return ContextMappingResult(ok=False, errors=[f"could not read the context: {exc}"])
            else:
                active = context
        if active is None:
            return ContextMappingResult(ok=False, errors=["document has no @context and none was given"])

        payload = {k: v for k, v in parsed.items() if k not in ("@context", "$schema")}
        return ContextMappingResult.model_validate(check_predicates(payload, active).to_dict(include_documents=True))
    finally:
        if doc_holder:
            doc_holder.cleanup()


class RuleWithEnforcement(Rule):
    """One catalogue rule, plus which check (if any) enforces it and where it is published."""

    enforced_by: str | None = Field(default=None, description="The check id that enforces this rule, if any.")
    spec_url: str = Field(description="Where this rule is defined in the published specification.")


class RulesListResult(BaseModel):
    """The normative rules the specification defines, and which checks enforce them."""

    meta_version: str | None = Field(default=None, description="Which meta-schema version the catalog came from.")
    count: int | None = Field(default=None, description="How many rules are listed.")
    rules: list[RuleWithEnforcement] = Field(default_factory=list, description="The matching rules.")
    error: str | None = Field(
        default=None, description="Set instead of rules when no catalog could be resolved or selected."
    )


@mcp.tool()
def list_oold_rules(
    meta: list[str] | None = None,
    area: str | None = None,
    unenforced_only: bool = False,
    offline: bool = False,
) -> RulesListResult:
    """List the normative rules the specification defines, and which checks enforce them.

    Every validation finding cites a rule id such as OOLD-RT-08f2; this resolves those ids to the
    requirement text, its level (MUST / SHOULD / ...), and the specification URL. Use it to
    explain a finding, or with unenforced_only to see which requirements the validator does not
    yet check.

    Args:
        meta: Meta-schema versions to read the catalog from. The catalog was introduced upstream
            after 0.8.0, so ["remote"] may be needed until a release ships it.
        area: Restrict to one area, e.g. RT (round-trip), CMP (composition), INS (instances).
        unenforced_only: Only machine-checkable rules that no check enforces yet.
        offline: Never fetch over the network.
    """
    from .check_registry import rule_map

    try:
        bundles = resolve_selection(tuple(meta) if meta else ("latest",), offline=offline)
    except MetaSchemaError as exc:
        return RulesListResult(error=str(exc))

    bundle = next((b for b in bundles if b.has_rules), None)
    if bundle is None:
        return RulesListResult(
            error=(
                f"meta-schema version(s) {', '.join(b.version for b in bundles)} ship no rule "
                "catalog; try meta=['remote']"
            )
        )

    enforced_by = {v: k for k, v in rule_map().items()}
    rules = bundle.machine_checkable_rules() if unenforced_only else bundle.rules
    if area:
        rules = [r for r in rules if r.area.upper() == area.upper()]
    if unenforced_only:
        rules = [r for r in rules if r.id not in enforced_by]

    return RulesListResult(
        meta_version=bundle.version,
        count=len(rules),
        rules=[
            RuleWithEnforcement(**r.model_dump(), enforced_by=enforced_by.get(r.id), spec_url=SPEC_RULE_URL + r.id)
            for r in rules
        ],
    )


class CheckSummary(BaseModel):
    """One check this validator can run, mirroring the public fields of check_registry.CheckInfo."""

    id: str = Field(description="The check id, e.g. lint.container.")
    summary: str = Field(description="What the check verifies.")
    rule: str | None = Field(default=None, description="The specification rule this check enforces, if any.")
    default_status: str = Field(
        description="ok, fail, warn, or skip: what a violation reports when no catalogue rule applies."
    )
    per_version: bool = Field(description="Whether this check's outcome can depend on the meta-schema version.")
    predates_catalog: bool = Field(
        description="Whether this check keeps running against a meta-schema version that ships no rule catalogue."
    )


class ChecksListResult(BaseModel):
    """The checks this validator can run, mirroring list_oold_rules for check ids."""

    count: int = Field(description="How many checks are listed.")
    checks: list[CheckSummary] = Field(default_factory=list, description="The matching checks.")


@mcp.tool()
def list_oold_checks(
    prefix: str | None = None,
    unmapped_only: bool = False,
) -> ChecksListResult:
    """List the checks this validator can run, mirroring list_oold_rules for check ids.

    A finding cites two identifiers: the check id (e.g. lint.container) names which check in this
    validator produced it, the rule id (e.g. OOLD-RT-08f2, see list_oold_rules) names the
    specification requirement it enforces, when it enforces one at all. Use unmapped_only to see
    the checks that enforce no rule - these are this validator's own methodology (satisfiability,
    round-trip, self-tests about the fixture suite) rather than a numbered requirement.

    Args:
        prefix: Only checks whose id starts with this, e.g. "lint.".
        unmapped_only: Only checks that enforce no specification rule.
    """
    from .check_registry import CHECKS

    checks = CHECKS
    if prefix:
        checks = [c for c in checks if c.id.startswith(prefix)]
    if unmapped_only:
        checks = [c for c in checks if not c.rule]

    return ChecksListResult(
        count=len(checks),
        checks=[
            CheckSummary(
                id=c.id,
                summary=c.summary,
                rule=c.rule,
                default_status=c.default_status,
                per_version=c.per_version,
                predates_catalog=c.predates_catalog,
            )
            for c in checks
        ],
    )


class MetaVersionsResult(BaseModel):
    """Tracked meta-schema versions, which one is `latest`, and the remote cache state."""

    tracked_dir: str | None = Field(default=None, description="Where the tracked meta-schema versions live on disk.")
    versions: list[dict[str, Any]] = Field(
        default_factory=list, description="Each tracked version, with its provenance from meta/index.json."
    )
    latest: str | None = Field(default=None, description="Which tracked version `latest` currently resolves to.")
    files: list[str] = Field(default_factory=list, description="The meta-schema file names loaded for a version.")
    remote: dict[str, Any] | None = Field(
        default=None,
        description="State of the unreleased `main` meta-schemas: base URL, cache dir, cached, fetched.",
    )
    error: str | None = Field(default=None, description="Set instead of the above when the store could not be read.")


@mcp.tool()
def list_meta_versions() -> MetaVersionsResult:
    """List the tracked meta-schema versions, which one is `latest`, and the remote cache state.

    Use this before choosing a `meta` argument for the validation tools.
    """
    try:
        return MetaVersionsResult.model_validate(describe_store())
    except MetaSchemaError as exc:
        return MetaVersionsResult(error=str(exc))


def main() -> None:
    """Run the server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
