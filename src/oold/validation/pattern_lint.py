"""Round-trip-safe ``@context`` pattern lint.

Ports ``meta/oold-pattern-lint.schema.json`` plus ``scripts/pattern_lint.mjs`` from oold-schema.
The lint has three parts, in two categories:

**MUST (a failure).**

* No term may coerce a literal to a datatype JSON encodes natively (``xsd:string``,
  ``xsd:boolean``, ``xsd:integer``, ``xsd:double``, ``xsd:float``). None of them survive a
  round-trip: ``xsd:string`` is RDF's default and is elided from plain literals, while
  boolean and numeric literals reconstruct as untyped native JSON values. Either way the value
  carries no ``@type`` coming back, the coercing term is never selected, and the property
  returns under its full IRI instead. This part *is* expressible in JSON Schema, so it lives in
  the versioned lint schema and is checked with a validator.
* A strictly ``type: array`` property must declare ``"@container": "@set"`` (or ``"@list"``),
  or a single-element array comes back as a scalar and the reconstruction fails re-validation.
  This correlates ``properties`` with ``@context``, so no single JSON Schema can express it and
  :func:`array_properties_missing_container` implements it directly.

**SHOULD (a warning).** A bare-IRI-string reference should constrain its lexical form with an
IRI/URI-family ``format``. The reference still round-trips without one, so this is a
recommendation rather than loss: :func:`iri_references_missing_format`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .formats import IRI_FORMATS
from .meta_store import MetaBundle
from .schema_checks import format_error


@dataclass
class PatternLintResult:
    """Findings for one schema against one meta-schema version."""

    meta_version: str
    schema_errors: list[str] = field(default_factory=list)
    missing_container: list[str] = field(default_factory=list)
    missing_iri_format: list[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        """MUST-level findings only. The IRI-format finding is a warning."""
        return bool(self.schema_errors or self.missing_container)

    @property
    def has_warning(self) -> bool:
        return bool(self.missing_iri_format)

    def to_dict(self) -> dict[str, Any]:
        return {
            "meta_version": self.meta_version,
            "schema_errors": self.schema_errors,
            "missing_container": self.missing_container,
            "missing_iri_format": self.missing_iri_format,
        }


def context_terms(context: Any, out: dict[str, dict[str, Any]] | None = None) -> dict[str, dict]:
    """Collect the object-valued term definitions of a ``@context``.

    The context may be a string, an array or an object. Keyword entries (``@vocab``,
    ``@version``, ...) are skipped, as are terms defined as a plain string, which carry no
    ``@container`` or ``@type`` to inspect.
    """
    if out is None:
        out = {}
    if isinstance(context, list):
        for entry in context:
            context_terms(entry, out)
        return out
    if isinstance(context, dict):
        for term, definition in context.items():
            if term.startswith("@"):
                continue
            if isinstance(definition, dict):
                out[term] = definition
    return out


def is_strict_array(prop: Any) -> bool:
    """True when a property accepts arrays and nothing else.

    A cardinality-flexible shape - ``type: ["array", "string"]``, or a ``oneOf``/``anyOf`` that
    also permits a scalar - is not strict: its scalar form still validates after a round-trip,
    so ``@container: @set`` is optional there (a MAY) rather than required.
    """
    if not isinstance(prop, dict):
        return False
    if prop.get("type") == "array":
        return True
    return ("items" in prop or "prefixItems" in prop) and prop.get("type") is None


def _has_container(definition: Any) -> bool:
    if not isinstance(definition, dict):
        return False
    container = definition.get("@container")
    # `@container` is legitimately either a string or an array of strings, so the string case
    # must be narrowed before any membership test: an unhashable list would otherwise raise.
    if isinstance(container, str):
        return container in {"@set", "@list"}
    if isinstance(container, list):
        return "@set" in container or "@list" in container
    return False


def array_properties_missing_container(schema: dict[str, Any]) -> list[str]:
    """Strict-array properties whose local ``@context`` term declares no ``@container``.

    Only locally declared properties mapped by a local term are in scope. A property mapped
    solely through an inherited (remote) context is checked when that context's own schema is
    linted.
    """
    terms = context_terms(schema.get("@context"))
    properties = schema.get("properties") or {}
    missing: list[str] = []
    for name, prop in properties.items():
        if not isinstance(prop, dict) or not is_strict_array(prop):
            continue
        if name in terms and not _has_container(terms[name]):
            missing.append(name)
    return missing


def iri_references_missing_format(schema: dict[str, Any]) -> list[str]:
    """IRI-valued reference properties that declare no IRI/URI-family ``format``.

    A bare IRI string (a value coerced to an IRI by ``@type: @id`` and typed by
    ``x-oold-range``) should constrain its form with ``iri-reference`` - which accepts absolute,
    compact and relative IRIs - or a stricter ``iri``/``uri-reference``/``uri``. Only
    string-valued ``@type: @id`` terms are in scope; value-form and object-valued (embedded)
    ranges are not.
    """
    terms = context_terms(schema.get("@context"))
    properties = schema.get("properties") or {}
    out: list[str] = []

    def has_range(node: Any) -> bool:
        return isinstance(node, dict) and "x-oold-range" in node

    for name, prop in properties.items():
        definition = terms.get(name)
        if not isinstance(prop, dict) or not isinstance(definition, dict):
            continue
        if definition.get("@type") != "@id":
            continue
        if prop.get("type") == "string" and has_range(prop) and prop.get("format") not in IRI_FORMATS:
            out.append(name)
            continue
        items = prop.get("items")
        if (
            isinstance(items, dict)
            and items.get("type") == "string"
            and has_range(items)
            and items.get("format") not in IRI_FORMATS
        ):
            out.append(f"{name}[]")
    return out


def lint(schema: dict[str, Any], bundle: MetaBundle) -> PatternLintResult:
    """Run all three lint parts against one schema."""
    result = PatternLintResult(meta_version=bundle.version)

    try:
        errors = sorted(
            bundle.pattern_lint_validator().iter_errors(schema),
            key=lambda e: list(e.absolute_path),
        )
        result.schema_errors = [format_error(error) for error in errors]
    except Exception as exc:
        result.schema_errors = [f"pattern lint could not run: {type(exc).__name__}: {exc}"]

    # These two correlate `properties` with `@context`, so they are not expressible in the lint
    # schema and are meta-version independent.
    result.missing_container = array_properties_missing_container(schema)
    result.missing_iri_format = iri_references_missing_format(schema)
    return result
