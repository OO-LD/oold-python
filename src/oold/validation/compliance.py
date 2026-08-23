"""The deterministic per-feature compliance suite.

Where the general workflow runs generic checks over any schema, this runs *fixtures with exact
expected outcomes*, so it catches behaviour a generic check cannot express.

A suite is a directory of JSON files, each holding a list of groups. A group is one of three
shapes:

``schemas``
    Candidate schemas checked against the OO-LD meta-schema, each asserting ``valid`` true or
    false. This is how every ``x-oold-*`` keyword gets a well-formedness test.

``lintSchemas``
    Candidate ``@context``\\ s checked against the round-trip pattern lint, same shape.

``tests``
    Per-feature cases against a schema named either by ``schemaRef`` (an example file, so real
    OO-LD composition is exercised through the loader) or inline via ``schema``. Each case may
    assert ``valid`` (instance validation), ``expectRdf`` (RDF dataset isomorphism),
    ``roundtrip`` (reconstruction equals the input), and ``expectErrorCode`` (processing must
    fail).

Finally, :func:`vocabulary_coverage` cross-checks that every keyword the meta-schemas define has
a well-formedness test, which is what keeps the suite honest as the vocabulary grows.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from pyld import jsonld

from .formats import OOLD_FORMAT_CHECKER
from .frame import embedded_properties, schema_to_frame
from .loader import DocumentLoader, describe_jsonld_error
from .meta_store import MetaBundle
from .pattern_lint import lint
from .roundtrip import canonical, json_equal
from .schema_checks import validate_against_meta

#: Base IRI assumed for inline compliance fixtures that declare no base of their own.
RDF_BASE = "https://oo-ld.test/"

#: Keyword prefixes the vocabulary-coverage check tracks.
VOCAB_PREFIXES = ("x-oold-", "x-enum-")

#: Keywords a meta-schema declares that the vocabulary check does not track, and why. A keyword
#: outside VOCAB_PREFIXES is invisible to coverage, so without this it would be dropped from the
#: count in silence and the report would still say "all N covered". Listing it here keeps the
#: exclusion in the report instead of in a reader's assumptions.
VOCAB_EXEMPT: dict[str, str] = {
    "x-sssom": "renamed to x-oold-sssom in 1.0.0-rc.2; only 1.0.0-rc.1 declares the old name",
}


def declared_x_keywords(bundle: MetaBundle) -> set[str]:
    """Every ``x-*`` key one version's meta-schemas declare, whatever the prefix.

    Mirrors :meth:`MetaBundle.declared_keywords`'s traversal - each document's own top-level
    ``properties``, plus the UI meta-schema's keyword block - but without its ``x-oold-*``
    pre-filter, so a keyword under any other prefix is still found. The difference between the
    two is exactly what coverage is not looking at.
    """
    found = {
        key
        for document in bundle.documents.values()
        for key in (document.get("properties") or {})
        if key.startswith("x-")
    }
    ui_keywords = (bundle.ui_meta.get("$defs") or {}).get("keywords", {}).get("properties") or {}
    found.update(key for key in ui_keywords if key.startswith("x-"))
    return found


def vocabulary_exemptions(bundle: MetaBundle) -> dict[str, str]:
    """The exempt keywords this version actually declares, mapped to the reason."""
    untracked = declared_x_keywords(bundle) - set(bundle.declared_keywords())
    return {key: VOCAB_EXEMPT[key] for key in sorted(untracked) if key in VOCAB_EXEMPT}


@dataclass
class ComplianceCase:
    """One assertion from a fixture, with what was expected and what happened."""

    file: str
    group: str
    description: str
    kind: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "file": self.file,
            "group": self.group,
            "description": self.description,
            "kind": self.kind,
            "passed": self.passed,
        }
        if self.detail:
            payload["detail"] = self.detail
        return payload


@dataclass
class ComplianceResult:
    """Everything one suite run produced."""

    cases: list[ComplianceCase] = field(default_factory=list)
    covered_keywords: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for case in self.cases if case.passed)

    @property
    def failed(self) -> list[ComplianceCase]:
        return [case for case in self.cases if not case.passed]

    def to_dict(self, include_documents: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "total": len(self.cases),
            "passed": self.passed,
            "failed": [case.to_dict() for case in self.failed],
            "errors": self.errors,
        }
        if include_documents:
            payload["cases"] = [case.to_dict() for case in self.cases]
        return payload


def collect_keywords(node: Any, found: set[str]) -> set[str]:
    """Every ``x-oold-*`` / ``x-enum-*`` keyword used anywhere in a document."""
    if isinstance(node, list):
        for item in node:
            collect_keywords(item, found)
    elif isinstance(node, dict):
        for key, value in node.items():
            if key.startswith(VOCAB_PREFIXES):
                found.add(key)
            collect_keywords(value, found)
    return found


def _instance_validator(schema: dict[str, Any]) -> Draft202012Validator:
    return Draft202012Validator(schema, format_checker=OOLD_FORMAT_CHECKER)


def _canonize(document: Any, options: dict[str, Any]) -> str:
    return jsonld.normalize(document, {"algorithm": "URDNA2015", **options}).strip()


def _error_code(exc: BaseException) -> str:
    """The identifying string of a JSON-LD error, matching how the reference reads it."""
    code = getattr(exc, "code", None)
    if code:
        return str(code)
    details = getattr(exc, "details", None) or {}
    if isinstance(details, dict) and details.get("code"):
        return str(details["code"])
    args = getattr(exc, "args", ())
    return args[0] if args and isinstance(args[0], str) else str(exc)


def run_suite(
    directory: Path,
    bundle: MetaBundle,
    loader: DocumentLoader,
    dereference: Callable[[str], dict[str, Any]] | None = None,
) -> ComplianceResult:
    """Run every fixture file in ``directory`` against one meta-schema version.

    ``dereference`` resolves a ``schemaRef`` to a dereferenced, bounded schema. Passing it is
    what lets a group exercise real OO-LD composition - base-class ``@context`` inheritance,
    property-``$ref`` scoped contexts - instead of only inline schemas. Groups using
    ``schemaRef`` are skipped when it is not supplied.
    """
    result = ComplianceResult()
    directory = Path(directory)
    if not directory.is_dir():
        result.errors.append(f"no compliance suite at {directory}")
        return result

    for path in sorted(directory.glob("*.json")):
        try:
            groups = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            result.errors.append(f"{path.name}: could not be read: {exc}")
            continue
        if not isinstance(groups, list):
            result.errors.append(f"{path.name}: expected a list of groups")
            continue
        for group in groups:
            if isinstance(group, dict):
                _run_group(path.name, group, bundle, loader, dereference, result)

    return result


def _run_group(
    filename: str,
    group: dict[str, Any],
    bundle: MetaBundle,
    loader: DocumentLoader,
    dereference: Callable[[str], dict[str, Any]] | None,
    result: ComplianceResult,
) -> None:
    label = group.get("feature") or group.get("description") or filename

    if isinstance(group.get("schemas"), list):
        for case in group["schemas"]:
            collect_keywords(case.get("schema"), result.covered_keywords)
            got = validate_against_meta(case.get("schema"), bundle).valid
            result.cases.append(
                ComplianceCase(
                    file=filename,
                    group=label,
                    description=case.get("description", ""),
                    kind="vocab",
                    passed=got == case.get("valid"),
                    detail=""
                    if got == case.get("valid")
                    else f"expected schema {'valid' if case.get('valid') else 'invalid'}, got "
                    f"{'valid' if got else 'invalid'}",
                )
            )
        return

    if isinstance(group.get("lintSchemas"), list):
        for case in group["lintSchemas"]:
            got = not lint(case.get("schema", {}), bundle).schema_errors
            result.cases.append(
                ComplianceCase(
                    file=filename,
                    group=label,
                    description=case.get("description", ""),
                    kind="lint",
                    passed=got == case.get("valid"),
                    detail=""
                    if got == case.get("valid")
                    else f"expected lint {'pass' if case.get('valid') else 'fail'}, got {'pass' if got else 'fail'}",
                )
            )
        return

    if isinstance(group.get("tests"), list):
        _run_tests(filename, label, group, bundle, loader, dereference, result)


def _run_tests(
    filename: str,
    label: str,
    group: dict[str, Any],
    bundle: MetaBundle,
    loader: DocumentLoader,
    dereference: Callable[[str], dict[str, Any]] | None,
    result: ComplianceResult,
) -> None:
    def record(description: str, kind: str, passed: bool, detail: str = "") -> None:
        result.cases.append(
            ComplianceCase(
                file=filename,
                group=label,
                description=description,
                kind=kind,
                passed=passed,
                detail=detail,
            )
        )

    context: Any = None
    rdf_base = RDF_BASE
    schema_ref = group.get("schemaRef")

    if schema_ref:
        if dereference is None:
            record(str(schema_ref), "setup", True, "skipped: no schema directory supplied")
            return
        try:
            feature_schema = dereference(schema_ref)
        except Exception as exc:
            record(str(schema_ref), "setup", False, f"could not dereference: {exc}")
            return
        validator = _instance_validator(feature_schema)
        rdf_base = loader.base_url
        frame_context = loader.url_for(schema_ref)
    else:
        inline_schema = group.get("schema") or {}
        meta_result = validate_against_meta(inline_schema, bundle)
        if not meta_result.valid:
            record(label, "setup", False, f"feature schema is invalid: {meta_result.errors[:2]}")
            return
        stripped = copy.deepcopy(inline_schema)
        stripped.pop("$schema", None)
        validator = _instance_validator(stripped)
        context = inline_schema.get("@context")
        feature_schema = inline_schema
        frame_context = context

    for test in group["tests"]:
        description = test.get("description", "")
        data = test.get("data")

        if "valid" in test:
            got = validator.is_valid(data)
            record(
                description,
                "validate",
                got == test["valid"],
                ""
                if got == test["valid"]
                else f"expected {'pass' if test['valid'] else 'fail'}, got {'pass' if got else 'fail'}",
            )

        if "expectRdf" in test:
            try:
                document = _document_for(data, context)
                got_rdf = _canonize(document, loader.options(base=rdf_base, format="application/n-quads"))
                want_rdf = _canonize(
                    test["expectRdf"],
                    {"inputFormat": "application/n-quads", "format": "application/n-quads"},
                )
                record(
                    description,
                    "rdf",
                    got_rdf == want_rdf,
                    "" if got_rdf == want_rdf else f"not isomorphic\n  got:  {got_rdf}\n  want: {want_rdf}",
                )
            except Exception as exc:
                record(description, "rdf", False, describe_jsonld_error(exc))

        if test.get("roundtrip"):
            try:
                document = _document_for(data, context)
                nquads = jsonld.to_rdf(document, loader.options(base=rdf_base, format="application/n-quads"))
                back = jsonld.from_rdf(nquads, {"format": "application/n-quads", "useNativeTypes": True})
                if embedded_properties(feature_schema):
                    restored = jsonld.frame(
                        back,
                        schema_to_frame(feature_schema, frame_context),
                        loader.options(base=rdf_base, omitDefault=True),
                    )
                else:
                    restored = jsonld.compact(back, frame_context, loader.options(base=rdf_base))
                same = json_equal(canonical(document), canonical(restored))
                record(
                    description,
                    "roundtrip",
                    same,
                    ""
                    if same
                    else f"instance != reconstruction\n  in:  {json.dumps(canonical(document))}"
                    f"\n  out: {json.dumps(canonical(restored))}",
                )
            except Exception as exc:
                record(description, "roundtrip", False, describe_jsonld_error(exc))

        if "expectErrorCode" in test:
            expected = test["expectErrorCode"]
            raised: BaseException | None = None
            try:
                jsonld.to_rdf(data, loader.options(base=rdf_base, format="application/n-quads"))
            except Exception as exc:
                raised = exc
            if raised is None:
                record(description, "error", False, f"did not throw (expected {expected!r})")
            else:
                code = _error_code(raised)
                passed = expected is True or str(expected) in str(code)
                record(
                    description,
                    "error",
                    passed,
                    "" if passed else f"threw {code!r}, expected {expected!r}",
                )


def _document_for(data: Any, context: Any) -> dict[str, Any]:
    """Attach the group's context unless the case carries its own, and drop ``$schema``.

    ``$schema`` is JSON Schema metadata, not JSON-LD data, so it must not reach the processor.
    """
    document = dict(data) if isinstance(data, dict) else {"@value": data}
    if "@context" not in document:
        document = {"@context": context, **document}
    document.pop("$schema", None)
    return document


def vocabulary_coverage(bundle: MetaBundle, covered: set[str]) -> list[str]:
    """Keywords the meta-schemas define but no fixture exercises.

    This is what keeps the suite in sync with the vocabulary: adding a keyword to a meta-schema
    without a well-formedness fixture fails the check.
    """
    return [keyword for keyword in bundle.declared_keywords() if keyword not in covered]
