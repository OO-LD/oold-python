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

try:
    # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # pragma: no cover - depends on the installed mcp major version
    # mcp 1.x, where the same class is called FastMCP. The parts used here - the `tool`
    # decorator and `run(transport=...)` - are identical across both.
    from mcp.server.fastmcp import FastMCP as _Server  # ty: ignore[unresolved-import]

from .generate import generate
from .meta_store import MetaSchemaError, describe_store
from .pipeline import Options, run_compliance, validate_directory, validate_instance, validate_schema
from .predicates import check_predicates
from .report import Report, failure_reasons
from .resolve import Resolver, SchemaResolutionError, bound_schema

mcp = _Server("oold-validation")

Verbosity = Literal["summary", "full"]


def _options(meta: list[str] | None, offline: bool) -> Options:
    return Options(meta=tuple(meta) if meta else ("latest",), offline=offline)


def _payload(report: Report, verbosity: Verbosity) -> dict[str, Any]:
    payload = report.to_dict(verbosity)
    payload["problems"] = failure_reasons(report)
    return payload


def _materialise(source: str, suffix: str) -> tuple[Path, tempfile.TemporaryDirectory | None]:
    """Turn a path or a raw JSON string into a file on disk.

    The checks are directory-relative by nature: a schema's ``@context`` and ``$ref`` entries are
    usually relative siblings. A schema passed as raw JSON therefore has to be written somewhere
    before it can be validated, and it will only resolve if it has no relative references.
    """
    text = source.strip()
    if not text.startswith("{"):
        return Path(source), None

    holder = tempfile.TemporaryDirectory(prefix="oold-validation-")
    name = "Inline" + suffix
    target = Path(holder.name) / name
    target.write_text(text, encoding="utf-8")
    return target, holder


@mcp.tool()
def validate_oold_schema(
    schema: str,
    meta: list[str] | None = None,
    offline: bool = False,
    verbosity: Verbosity = "summary",
) -> dict[str, Any]:
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

    The fields that matter most are `summary` (counts and the verdict) and `problems`, which
    lists each failure in readable form.
    """
    path, holder = _materialise(schema, ".schema.json")
    try:
        return _payload(validate_schema(path, _options(meta, offline)), verbosity)
    except MetaSchemaError as exc:
        return {"passed": False, "fatal_error": str(exc)}
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
) -> dict[str, Any]:
    """Check whether a specific document conforms to an OO-LD schema.

    Validates the instance structurally against its schema, with formats asserted, then projects
    it to RDF and back to confirm the reconstruction is identical. This answers "does this
    document conform", as opposed to "is this schema sound".

    Args:
        instance: Path to the instance document. It names its schema with $schema.
        schema: Optional path to a schema, overriding $schema. Must sit in the same directory as
            the instance so relative @context references resolve.
        meta: Meta-schema versions, as in validate_oold_schema.
        offline: Never fetch over the network.
        verbosity: "full" adds the canonical forms of both sides of the round-trip.
    """
    try:
        report = validate_instance(Path(instance), Path(schema) if schema else None, _options(meta, offline))
    except MetaSchemaError as exc:
        return {"passed": False, "fatal_error": str(exc)}
    return _payload(report, verbosity)


@mcp.tool()
def validate_oold_directory(
    directory: str,
    meta: list[str] | None = None,
    offline: bool = False,
    verbosity: Verbosity = "summary",
) -> dict[str, Any]:
    """Validate every *.schema.json and *.instance.json in a directory.

    The same general-workflow tier the reference harness exposes as `oold-validate <dir>`, so a
    downstream repository can conformance-check its generated schemas.

    Args:
        directory: The directory to validate.
        meta: Meta-schema versions, as in validate_oold_schema.
        offline: Never fetch over the network.
        verbosity: "full" adds per-check detail.
    """
    try:
        report = validate_directory(Path(directory), _options(meta, offline))
    except MetaSchemaError as exc:
        return {"passed": False, "fatal_error": str(exc)}
    return _payload(report, verbosity)


@mcp.tool()
def run_oold_compliance(
    directory: str,
    meta: list[str] | None = None,
    offline: bool = False,
    verbosity: Verbosity = "summary",
) -> dict[str, Any]:
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
        return {"passed": False, "fatal_error": str(exc)}
    return _payload(report, verbosity)


@mcp.tool()
def generate_oold_instance(schema: str, offline: bool = False) -> dict[str, Any]:
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
        return {"ok": False, "instance": None, "error": str(exc)}
    finally:
        if holder:
            holder.cleanup()

    return {
        "ok": result.ok,
        "instance": result.instance,
        "notes": result.notes,
        "error": result.error,
        "unresolved_refs": deref.unresolved,
    }


@mcp.tool()
def check_context_mapping(document: str, context: str | None = None) -> dict[str, Any]:
    """Report which properties of a JSON-LD document carry meaning, and which do not.

    No schema and no generation involved. Two failure modes are distinguished: a property that
    expands to nothing (`dropped`, it has no @context term) and one that expands to a
    non-absolute IRI (`suspicious`, its prefix is probably undefined). The second is the
    dangerous one, because the document looks fine and round-trips cleanly while pointing at a
    meaningless predicate.

    Args:
        document: The JSON-LD document, as a JSON string or a path to one.
        context: Optional context as a JSON string, overriding the document's own @context.
    """
    text = document.strip()
    if text.startswith("{"):
        parsed = json.loads(text)
    else:
        try:
            parsed = json.loads(Path(document).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "errors": [f"could not read the document: {exc}"]}

    active = parsed.get("@context")
    if context is not None:
        try:
            active = json.loads(context) if context.strip().startswith(("{", "[")) else context
        except json.JSONDecodeError as exc:
            return {"ok": False, "errors": [f"context is not valid JSON: {exc}"]}
    if active is None:
        return {"ok": False, "errors": ["document has no @context and none was given"]}

    payload = {k: v for k, v in parsed.items() if k not in ("@context", "$schema")}
    return check_predicates(payload, active).to_dict(include_documents=True)


@mcp.tool()
def list_meta_versions() -> dict[str, Any]:
    """List the tracked meta-schema versions, which one is `latest`, and the remote cache state.

    Use this before choosing a `meta` argument for the validation tools.
    """
    try:
        return describe_store()
    except MetaSchemaError as exc:
        return {"error": str(exc)}


def main() -> None:
    """Run the server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
