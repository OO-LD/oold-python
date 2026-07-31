"""Deterministic instance generation.

The reference harness generates instances with json-schema-faker configured as
``{alwaysFakeOptionals: true, useExamplesValue: true, useDefaultValue: true, maxItems: 1,
maxLength: 40}`` (``validate.mjs`` lines 112-120). ``alwaysFakeOptionals`` is the important part:
it means every property is populated, not a random subset. So the reference is already
generating a *maximal* instance, and this module reproduces that deterministically instead of
sampling.

Determinism is a real gain rather than a compromise. The generated instance is what the
satisfiability and round-trip checks run on, and a randomised one turns a round-trip bug into a
flaky CI failure that reproduces only sometimes.

Two things the generator must get right, both learned from the reference implementation:

* a cut node (:data:`~oold.validation.resolve.CUT_SCHEMA`) must produce a *string*. At a typeless
  node a random generator is free to emit a boolean or a number, and a non-string under an
  ``@type: "@id"`` term becomes an RDF literal that cannot compact back, which reads as a false
  round-trip loss.
* generated ``id`` values must be unique. The reference's faker draws URLs from a small pool, so
  two ``id`` values in one document can collide, and in RDF the same IRI is the same node: a
  colliding embed merges into its parent and the round-trip then faithfully reports the merged
  graph, which reads as a false schema failure. See :func:`uniquify_ids`.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from .formats import FORMAT_SAMPLES
from .resolve import CUT_FORMAT

#: Matches the reference faker's ``maxLength``/``maxItems`` settings.
MAX_LENGTH = 40
MAX_ITEMS = 1

#: How many oneOf/anyOf branches to enumerate per schema. A large schema can have hundreds, and
#: each one means a full schema copy, so the reference caps this and notes when it does.
MAX_VARIANTS = 50

#: Guard against a schema that is deep but not cyclic. ``bound_schema`` has already cut cycles,
#: so this only ever bites on genuinely deep nesting.
MAX_DEPTH = 40

_DEFAULT_STRING = "example"


@dataclass
class GenerationResult:
    """One generated instance, plus anything worth reporting about how it was built."""

    instance: Any = None
    notes: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dict(self, include_documents: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {"ok": self.ok, "notes": self.notes}
        if self.error:
            payload["error"] = self.error
        if include_documents:
            payload["instance"] = self.instance
        return payload


@dataclass
class Variant:
    """One ``oneOf``/``anyOf`` branch, pinned so it is the only reachable alternative."""

    label: str
    schema: dict[str, Any]


class _Counter:
    """Per-run counters, so distinct cut nodes and ids do not collapse onto one RDF node."""

    def __init__(self) -> None:
        self.cut = 0
        self.identifier = 0
        #: Object identities of generated dicts whose ``id`` came from the schema author
        #: (``const``/``enum``/``default``/``examples``) rather than from this generator.
        #: Those must not be rewritten. Held by identity, which is safe because every entry is
        #: reachable from the instance being built and so stays alive.
        self.pinned_ids: set[int] = set()

    def next_cut(self) -> str:
        value = f"https://oo-ld.test/cut/{self.cut}"
        self.cut += 1
        return value

    def next_id(self) -> str:
        # A distinct authority from the document base, or compaction relativises the id against
        # the base and breaks strict `format: iri` schemas.
        value = f"https://instances.example.org/id/{self.identifier}"
        self.identifier += 1
        return value


# ---------------------------------------------------------------------------- composition


def _merge_all_of(node: dict[str, Any]) -> dict[str, Any]:
    """Flatten ``allOf`` into one effective schema.

    OO-LD models inheritance as ``allOf: [{"$ref": "Parent.schema.json"}]``, so after
    dereferencing a subclass's inherited properties live inside ``allOf`` rather than at the top
    level. Generating without flattening would miss most of the schema.
    """
    if not isinstance(node.get("allOf"), list):
        return node

    merged: dict[str, Any] = {k: v for k, v in node.items() if k != "allOf"}
    properties: dict[str, Any] = dict(merged.get("properties") or {})
    required: list[str] = list(merged.get("required") or [])

    for branch in node["allOf"]:
        if not isinstance(branch, dict):
            continue
        flattened = _merge_all_of(branch)
        for key, value in flattened.items():
            if key == "properties" and isinstance(value, dict):
                for name, sub in value.items():
                    properties.setdefault(name, sub)
            elif key == "required" and isinstance(value, list):
                required.extend(r for r in value if r not in required)
            else:
                merged.setdefault(key, value)

    if properties:
        merged["properties"] = properties
    if required:
        merged["required"] = required
    return merged


def _effective(node: dict[str, Any]) -> dict[str, Any]:
    """Resolve composition down to a single schema: ``allOf`` merged, first branch pinned."""
    merged = _merge_all_of(node)
    for keyword in ("oneOf", "anyOf"):
        branches = merged.get(keyword)
        if isinstance(branches, list) and branches:
            chosen = branches[0] if isinstance(branches[0], dict) else {}
            rest = {k: v for k, v in merged.items() if k not in ("oneOf", "anyOf")}
            combined = dict(rest)
            for key, value in chosen.items():
                combined[key] = value
            if "properties" in rest and "properties" in chosen:
                combined["properties"] = {**rest["properties"], **chosen["properties"]}
            return _effective(combined)
    return merged


# ---------------------------------------------------------------------------- scalars


def _string_value(node: dict[str, Any], counter: _Counter) -> str:
    fmt = node.get("format")
    if fmt == CUT_FORMAT:
        return counter.next_cut()
    if isinstance(fmt, str) and fmt in FORMAT_SAMPLES:
        return FORMAT_SAMPLES[fmt]

    value = _DEFAULT_STRING
    minimum = node.get("minLength")
    if isinstance(minimum, int) and minimum > len(value):
        value += "x" * (minimum - len(value))
    maximum = node.get("maxLength")
    limit = MAX_LENGTH if not isinstance(maximum, int) else min(maximum, MAX_LENGTH)
    if len(value) > limit:
        value = value[:limit]
    return value


def _number_value(node: dict[str, Any], integer: bool) -> Any:
    value: Any = 0
    if "minimum" in node and isinstance(node["minimum"], (int, float)):
        value = node["minimum"]
    elif "exclusiveMinimum" in node and isinstance(node["exclusiveMinimum"], (int, float)):
        value = node["exclusiveMinimum"] + 1

    maximum = node.get("maximum")
    if isinstance(maximum, (int, float)) and value > maximum:
        value = maximum
    exclusive_max = node.get("exclusiveMaximum")
    if isinstance(exclusive_max, (int, float)) and value >= exclusive_max:
        value = exclusive_max - 1

    multiple = node.get("multipleOf")
    if isinstance(multiple, (int, float)) and multiple > 0:
        steps = -(-value // multiple) if value > 0 else 0
        value = steps * multiple

    return int(value) if integer else float(value)


def _infer_type(node: dict[str, Any]) -> str:
    declared = node.get("type")
    if isinstance(declared, list):
        declared = next((t for t in declared if isinstance(t, str)), None)
    if isinstance(declared, str):
        return declared
    if "properties" in node or "required" in node:
        return "object"
    if "items" in node or "prefixItems" in node:
        return "array"
    # A node carrying only a `format` is a string, which is what makes the cut marker render as
    # one. A node carrying nothing at all accepts anything, and a string is the safest choice:
    # it round-trips under any term, as an IRI reference under @id or a literal under a plain
    # term, whereas a boolean or number under an @id-coerced term cannot compact back.
    return "string"


# ---------------------------------------------------------------------------- generation


def _generate(node: Any, counter: _Counter, depth: int) -> Any:
    if node is True or node == {}:
        return _DEFAULT_STRING
    if node is False or not isinstance(node, dict):
        return None
    if depth > MAX_DEPTH:
        return None

    node = _effective(node)

    # Author-provided values win, in the order json-schema-faker applies them.
    if "const" in node:
        return copy.deepcopy(node["const"])
    if "default" in node:
        return copy.deepcopy(node["default"])
    examples = node.get("examples")
    if isinstance(examples, list) and examples:
        return copy.deepcopy(examples[0])
    enum = node.get("enum")
    if isinstance(enum, list) and enum:
        return copy.deepcopy(enum[0])

    kind = _infer_type(node)

    if kind == "object":
        out: dict[str, Any] = {}
        for name, sub in (node.get("properties") or {}).items():
            value = _generate(sub, counter, depth + 1)
            if value is not None or _allows_null(sub):
                out[name] = value
        if _is_authored(node.get("properties", {}).get("id")):
            counter.pinned_ids.add(id(out))
        return out

    if kind == "array":
        items = node.get("items")
        prefix = node.get("prefixItems")
        values: list[Any] = []
        if isinstance(prefix, list):
            values.extend(_generate(entry, counter, depth + 1) for entry in prefix)
        min_items = node.get("minItems") if isinstance(node.get("minItems"), int) else 0
        max_items = node.get("maxItems") if isinstance(node.get("maxItems"), int) else MAX_ITEMS
        wanted = max(min_items, min(MAX_ITEMS, max_items))
        if items is not None:
            while len(values) < wanted:
                values.append(_generate(items, counter, depth + 1))
        return values[:max_items] if isinstance(node.get("maxItems"), int) else values

    if kind == "boolean":
        return True
    if kind == "null":
        return None
    if kind in ("number", "integer"):
        return _number_value(node, integer=kind == "integer")
    return _string_value(node, counter)


def _allows_null(sub: Any) -> bool:
    if not isinstance(sub, dict):
        return False
    declared = sub.get("type")
    return declared == "null" or (isinstance(declared, list) and "null" in declared)


def _is_authored(subschema: Any) -> bool:
    """True when a subschema pins its value, so the generator did not choose it.

    Mirrors the precedence in :func:`_generate`: ``const`` and ``default`` count even when the
    pinned value is falsy, while ``examples``/``enum`` need a non-empty list to apply.
    """
    if not isinstance(subschema, dict):
        return False
    if "const" in subschema or "default" in subschema:
        return True
    return bool(subschema.get("examples")) or bool(subschema.get("enum"))


def uniquify_ids(value: Any, counter: _Counter) -> Any:
    """Give every generated ``id`` a distinct value.

    Port of ``uniquifyIds`` (``validate.mjs`` lines 422-432). Colliding ``id`` values are not a
    cosmetic problem: in RDF the same IRI is the same node, so a colliding embed merges into its
    parent and the round-trip then faithfully reports the merged graph, which reads as a false
    schema failure.

    One deliberate refinement over the reference, which rewrites unconditionally: an ``id`` the
    schema pinned itself (``const``, ``enum``, ``default``, ``examples``) is left alone.
    Overwriting it would make the generated instance violate its own schema and report a
    satisfiability failure that says nothing about the schema.
    """
    if isinstance(value, list):
        for item in value:
            uniquify_ids(item, counter)
    elif isinstance(value, dict):
        if isinstance(value.get("id"), str) and id(value) not in counter.pinned_ids:
            value["id"] = counter.next_id()
        for item in value.values():
            uniquify_ids(item, counter)
    return value


def generate(schema: dict[str, Any], unique_ids: bool = True) -> GenerationResult:
    """Generate one maximal instance from a dereferenced, bounded schema."""
    result = GenerationResult()
    counter = _Counter()
    try:
        instance = _generate(schema, counter, 0)
    except RecursionError:
        result.error = "generation recursed too deeply; the schema may not be fully bounded"
        return result
    except Exception as exc:
        result.error = f"generation failed: {type(exc).__name__}: {exc}"
        return result

    if unique_ids:
        uniquify_ids(instance, counter)
    result.instance = instance
    if counter.cut:
        result.notes.append(
            f"{counter.cut} cut node(s) were populated with a placeholder IRI; the schema has "
            "cycles or exceeds the depth budget"
        )
    return result


# ---------------------------------------------------------------------------- variants

_SUB_DICT = ("properties", "$defs", "definitions", "patternProperties")
_SUB_VAL = ("items", "additionalProperties", "not", "if", "then", "else", "contains", "propertyNames")
_SUB_LIST = ("allOf", "oneOf", "anyOf", "prefixItems")


def collect_variants(schema: dict[str, Any], limit: int = MAX_VARIANTS) -> tuple[list[Variant], int]:
    """Enumerate one schema variant per ``oneOf``/``anyOf`` branch.

    Port of ``collectVariants`` (``validate.mjs`` lines 329-356). Each variant pins one branch by
    replacing the alternatives with a single-element list, which is how the reference gets
    deterministic per-branch coverage out of a random generator. Here generation is already
    deterministic, but pinning is still what makes the *other* branches reachable at all: without
    it only branch 0 is ever exercised.

    Returns the variants (capped at ``limit``) and the total number found, so a caller can report
    that it truncated.
    """
    variants: list[Variant] = []

    def walk(node: Any, path: list[Any]) -> None:
        if not isinstance(node, dict):
            return
        for keyword in ("oneOf", "anyOf"):
            branches = node.get(keyword)
            if isinstance(branches, list) and len(branches) > 1:
                for index in range(len(branches)):
                    clone = copy.deepcopy(schema)
                    target = clone
                    for key in path:
                        target = target[key]
                    target[keyword] = [copy.deepcopy(branches[index])]
                    label = "/".join(str(p) for p in path) or "<root>"
                    variants.append(Variant(label=f"{label}/{keyword}[{index}]", schema=clone))

        for key, value in node.items():
            if not isinstance(value, (dict, list)):
                continue
            if key in _SUB_DICT and isinstance(value, dict):
                for name, sub in value.items():
                    walk(sub, [*path, key, name])
            elif key in _SUB_VAL and isinstance(value, dict):
                walk(value, [*path, key])
            elif key in _SUB_LIST and isinstance(value, list):
                for index, sub in enumerate(value):
                    walk(sub, [*path, key, index])

    walk(schema, [])
    return variants[:limit], len(variants)
