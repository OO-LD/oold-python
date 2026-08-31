"""Schema-level checks: meta-schema well-formedness and ``$ref`` composition.

A schema is a well-formed OO-LD schema when it validates against the OO-LD meta-schema, and its
standard ``$ref`` composition resolves.

The OO-LD meta-schema is 2020-12 plus the OO-LD and UI vocabularies, and it declares those
vocabularies optional so a generic 2020-12 validator still processes OO-LD schemas. Validating
against it therefore subsumes plain 2020-12 validation; there is no separate dialect check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from .meta_store import MetaBundle
from .resolve import DereferenceResult, ResolvedSchema, Resolver

#: JSON-LD keywords this check watches for at the root of a schema document. Only ``@context``
#: belongs there for an OO-LD schema; ``@vocab``, ``@base`` and ``@version`` are context-internal
#: keywords, and ``@id``, ``@type`` and ``@graph`` are instance-level, so none of the other six
#: has legitimate business at a schema root - across the corpus, none ever appears there. They
#: are unknown keywords as far as JSON Schema is concerned, and 2020-12 tolerates unknown
#: keywords as annotations, which is what lets an OO-LD schema be a valid JSON Schema at all and
#: is why one appearing here does not fail meta-schema validation on its own; the whole set is
#: kept so that one showing up at the root is at least reported as a JSON-LD keyword rather than
#: passing unnoticed. That tolerance is load-bearing for this whole package, so the test suite
#: asserts it directly rather than assuming it.
JSONLD_KEYWORDS = frozenset({"@context", "@id", "@type", "@graph", "@vocab", "@base", "@version"})

#: Cap on how many meta-schema errors are reported for one schema. A single structural mistake
#: high in a document can produce hundreds of downstream errors, which buries the useful one.
MAX_REPORTED_ERRORS = 20


@dataclass
class MetaValidationResult:
    """Outcome of validating one schema against one meta-schema version."""

    valid: bool
    meta_version: str
    errors: list[str] = field(default_factory=list)
    truncated: int = 0
    declared_dialect: str | None = None
    jsonld_keywords_found: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "valid": self.valid,
            "meta_version": self.meta_version,
            "errors": self.errors,
            "declared_dialect": self.declared_dialect,
            "jsonld_keywords_found": self.jsonld_keywords_found,
        }
        if self.truncated:
            payload["errors_omitted"] = self.truncated
        return payload


def format_error(error: Any) -> str:
    """Render a validation error with the instance location that produced it."""
    location = "/".join(str(part) for part in error.absolute_path)
    prefix = f"at /{location}: " if location else ""
    return f"{prefix}{error.message}"


def validate_against_meta(schema: Any, bundle: MetaBundle) -> MetaValidationResult:
    """Validate a schema document against the OO-LD meta-schema of one version.

    Errors come back as data, never as exceptions: a caller asking about a broken schema wants
    the explanation, which is exactly the case where raising would destroy the answer.
    """
    if not isinstance(schema, dict):
        return MetaValidationResult(
            valid=False,
            meta_version=bundle.version,
            errors=[f"schema root must be a JSON object, got {type(schema).__name__}"],
        )

    declared = schema.get("$schema")
    found = sorted(key for key in schema if key in JSONLD_KEYWORDS)

    try:
        raw = sorted(
            bundle.meta_validator().iter_errors(schema),
            key=lambda e: list(e.absolute_path),
        )
    # `schema` here is a candidate document straight off disk, not yet known to be well-formed
    # in any way, and iter_errors walks it as jsonschema instance data: a malformed keyword
    # value (say `"properties": "x"`) surfaces as a plain AttributeError/TypeError from
    # jsonschema's internals, and an unresolvable `$ref` as a referencing.exceptions.Unresolvable
    # subclass, not a ValidationError - so no jsonschema-specific type covers this. The docstring
    # above commits this function to never raising, which is what a broken-schema caller needs.
    except Exception as exc:
        return MetaValidationResult(
            valid=False,
            meta_version=bundle.version,
            errors=[f"meta-schema validation could not run: {type(exc).__name__}: {exc}"],
            declared_dialect=declared,
            jsonld_keywords_found=found,
        )

    messages = [format_error(error) for error in raw]
    truncated = max(0, len(messages) - MAX_REPORTED_ERRORS)
    return MetaValidationResult(
        valid=not messages,
        meta_version=bundle.version,
        errors=messages[:MAX_REPORTED_ERRORS],
        truncated=truncated,
        declared_dialect=declared,
        jsonld_keywords_found=found,
    )


def check_usable_as_validator(schema: Any) -> list[str]:
    """Check the schema can actually be compiled into a validator.

    Meta-schema validity and usability are not the same thing. A schema can satisfy the
    meta-schema and still fail to compile, for instance through a malformed regex in
    ``pattern``, so this is checked separately and explicitly.
    """
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return [f"schema does not compile: {exc.message}"]
    return []


def check_refs_resolve(resolver: Resolver, resolved: ResolvedSchema) -> tuple[DereferenceResult, list[str]]:
    """Dereference a schema's ``$ref`` composition, reporting anything that did not resolve.

    Follows remote references as well as local ones. Results are cached.
    """
    result = resolver.dereference(resolved)
    return result, list(result.unresolved)
