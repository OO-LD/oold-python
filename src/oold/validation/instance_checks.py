"""Checks on a committed instance document.

Ports two sections of the reference harness:

* ``validate.mjs`` lines 408-416 - the instance validates against its schema, with ``format``
  asserted rather than annotated;
* ``validate.mjs`` lines 476-503 - the instance survives ``instance -> RDF -> instance``
  unchanged.

An instance names its schema with ``$schema``, resolved relative to the instance's own location,
so a directory of instances validates with no further configuration. The round-trip here uses
the full :func:`~oold.validation.roundtrip.canonical` comparison rather than the keys-only one:
for a document someone actually wrote, the values matter too, not just that the keys survived.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator
from pyld import jsonld

from .formats import OOLD_FORMAT_CHECKER
from .frame import embedded_properties, schema_to_frame
from .loader import DocumentLoader, describe_jsonld_error
from .roundtrip import canonical, json_equal
from .schema_checks import format_error


@dataclass
class InstanceCheckResult:
    """Structural validation of one instance against its schema."""

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    schema_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "errors": self.errors, "schema_ref": self.schema_ref}


@dataclass
class InstanceRoundtripResult:
    """One committed instance through RDF and back, compared in full."""

    ok: bool = False
    lossless: bool = False
    triples: int = 0
    method: str = ""
    error: str | None = None
    restored: Any = None
    original_canonical: Any = None
    restored_canonical: Any = None

    def to_dict(self, include_documents: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "lossless": self.lossless,
            "triples": self.triples,
            "method": self.method,
        }
        if self.error:
            payload["error"] = self.error
        if include_documents:
            payload["restored"] = self.restored
            payload["original_canonical"] = self.original_canonical
            payload["restored_canonical"] = self.restored_canonical
        return payload


def validate_instance(instance: Any, schema: dict[str, Any]) -> InstanceCheckResult:
    """Validate an instance against its dereferenced, bounded schema.

    The whole document is validated, ``@context`` and ``$schema`` included. OO-LD schemas allow
    additional properties, so those keys pass as unconstrained extras, exactly as they do under
    the reference harness.
    """
    result = InstanceCheckResult(schema_ref=instance.get("$schema") if isinstance(instance, dict) else None)
    try:
        validator = Draft202012Validator(schema, format_checker=OOLD_FORMAT_CHECKER)
        errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    except Exception as exc:
        result.valid = False
        result.errors = [f"could not validate against the schema: {type(exc).__name__}: {exc}"]
        return result

    result.errors = [format_error(error) for error in errors]
    result.valid = not result.errors
    return result


def roundtrip_instance(
    instance: dict[str, Any],
    schema: dict[str, Any],
    loader: DocumentLoader,
    instance_url: str,
    schema_url: str,
) -> InstanceRoundtripResult:
    """Project a committed instance to RDF and reconstruct it.

    The instance is used as written: it carries its own ``@context``, so nothing is injected.
    Reconstruction uses the schema-derived frame when the schema embeds objects, and plain
    compaction otherwise, because compaction alone never re-nests a flattened graph.
    """
    result = InstanceRoundtripResult()
    try:
        nquads = jsonld.to_rdf(instance, loader.options(base=instance_url, format="application/n-quads"))
        result.triples = sum(1 for line in nquads.split("\n") if line.strip())
        if not result.triples:
            result.error = "produced no triples"
            return result

        back = jsonld.from_rdf(nquads, {"format": "application/n-quads", "useNativeTypes": True})

        if embedded_properties(schema):
            result.method = "framed"
            result.restored = jsonld.frame(
                back,
                schema_to_frame(schema, schema_url),
                loader.options(base=instance_url, omitDefault=True),
            )
        else:
            result.method = "compacted"
            result.restored = jsonld.compact(back, schema_url, loader.options(base=instance_url))
    except Exception as exc:
        result.error = describe_jsonld_error(exc)
        return result

    result.original_canonical = canonical(instance)
    result.restored_canonical = canonical(result.restored)
    result.lossless = json_equal(result.original_canonical, result.restored_canonical)
    result.ok = result.lossless
    return result
