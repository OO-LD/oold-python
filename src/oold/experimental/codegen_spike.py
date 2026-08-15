"""Spike: IR-based code generation for OO-LD schemas.

Companion to ``docs/design/graph-object-binding.md`` section 0c ("own generator
vs datamodel-code-generator"). It shows that the three structural problems the
current toolchain fights with regex on generated *text* -

1. multiple ``allOf`` inheritance (``osw-python-package-generator``'s
   ``_fix_missing_allof_bases``),
2. class reuse / dedup by ``x-oold-uuid`` (the UUID-dedup passes in
   ``replace_duplicated_classes_with_imports``),
3. typed ``x-oold-range`` references,

- fall out for free when you generate from an explicit intermediate
representation (IR) instead. The schema graph is parsed once into ``ClassIR`` /
``FieldIR`` nodes; identity is resolved structurally by ``x-oold-uuid``; the
emitter then prints idiomatic pydantic once. There is **no** text
post-processing.

The emitter targets the ``Ref[T]`` binding from ``ref_binding.py``, so the two
spikes compose: the recommended generator emits the recommended binding.

Run it::

    python -m oold.experimental.codegen_spike

It prints the generated module, executes it, and self-checks the three
properties above.

Scope: intentionally minimal (string/scalar types, the IRI form of
``x-oold-range``, single-file output). It is a feasibility probe, not the
Phase-2 generator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Intermediate representation


@dataclass
class FieldIR:
    name: str
    py_type: str  # e.g. "str", "Ref[Person]"
    required: bool = False
    default_repr: Optional[str] = None  # source text for the default, if any


@dataclass
class ClassIR:
    name: str
    uuid: Optional[str] = None
    x_oold_iri: Optional[str] = None
    bases: List[str] = field(default_factory=list)  # resolved base class names
    fields: List[FieldIR] = field(default_factory=list)


_JSON_TO_PY = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
}


def _read_range(prop: dict) -> Optional[object]:
    """Dual-read the range keyword (x-oold-range canonical, legacy 'range')."""
    if "x-oold-range" in prop:
        return prop["x-oold-range"]
    return prop.get("range")


def _title_of_ref(ref: str) -> str:
    """Reduce a $ref / range IRI to a schema title (last path segment, no ext)."""
    tail = ref.rstrip("/").split("/")[-1]
    for ext in (".schema.json", ".json"):
        if tail.endswith(ext):
            tail = tail[: -len(ext)]
    return tail


# Front end: schema graph to IR


def build_ir(schemas: Dict[str, dict]) -> List[ClassIR]:
    """Turn a set of OO-LD schemas (keyed by title) into ordered ClassIR nodes.

    Identity is resolved by ``x-oold-uuid``: the first schema carrying a UUID
    is canonical; any later schema with the same UUID is an *alias* and does
    not produce its own class. References to an alias resolve to the canonical
    class. This is the structural equivalent of the generator's UUID-dedup
    regex passes.
    """
    # 1. Resolve x-oold-uuid identity -> canonical class name per title.
    uuid_to_canonical: Dict[str, str] = {}
    title_to_class: Dict[str, str] = {}
    for title, schema in schemas.items():
        uuid = schema.get("x-oold-uuid") or schema.get("uuid")
        if uuid and uuid in uuid_to_canonical:
            title_to_class[title] = uuid_to_canonical[uuid]  # alias -> canonical
        else:
            cls_name = schema.get("title", title)
            title_to_class[title] = cls_name
            if uuid:
                uuid_to_canonical[uuid] = cls_name

    def resolve(ref: str) -> str:
        title = _title_of_ref(ref)
        return title_to_class.get(title, title)

    # 2. Build one ClassIR per *canonical* title.
    seen: set = set()
    irs: List[ClassIR] = []
    for title, schema in schemas.items():
        cls_name = title_to_class[title]
        if cls_name in seen:
            continue  # alias or duplicate - already represented
        seen.add(cls_name)

        cir = ClassIR(
            name=cls_name,
            uuid=schema.get("x-oold-uuid") or schema.get("uuid"),
            x_oold_iri=schema.get("x-oold-iri") or schema.get("iri"),
        )

        # allOf -> multiple inheritance (each $ref becomes a base class).
        for entry in schema.get("allOf", []):
            if "$ref" in entry:
                cir.bases.append(resolve(entry["$ref"]))

        required = set(schema.get("required", []))
        for pname, prop in schema.get("properties", {}).items():
            cir.fields.append(_field_ir(pname, prop, pname in required, resolve))

        irs.append(cir)

    return irs


def _field_ir(pname: str, prop: dict, required: bool, resolve) -> FieldIR:
    rng = _read_range(prop)
    if rng is not None:
        # x-oold-range: typed reference. IRI form (str) and array-of-IRI form
        # are handled; an inline-subschema form would recurse (out of scope).
        if isinstance(rng, str):
            target = resolve(rng)
        elif isinstance(rng, list) and rng:
            target = resolve(rng[0])  # union collapses to first for the spike
        else:
            target = "object"
        py_type = f"Ref[{target}]"
    else:
        py_type = _JSON_TO_PY.get(prop.get("type", "string"), "str")

    default_repr = None
    if "default" in prop:
        default_repr = repr(prop["default"])
    elif not required:
        default_repr = "None"

    return FieldIR(
        name=pname,
        py_type=py_type,
        required=required,
        default_repr=default_repr,
    )


# Back end: IR to pydantic source (single pass, no text post-processing)


def emit(irs: List[ClassIR]) -> str:
    lines: List[str] = [
        '"""Generated by oold.experimental.codegen_spike - do not edit."""',
        "from __future__ import annotations",
        "",
        "from typing import ClassVar, Optional",
        "",
        "from oold.experimental.ref_binding import OoldModel, Ref",
        "",
    ]
    for cir in irs:
        bases = ", ".join(cir.bases) if cir.bases else "OoldModel"
        lines.append(f"class {cir.name}({bases}):")
        body_start = len(lines)
        if cir.x_oold_iri:
            lines.append(f"    x_oold_iri: ClassVar[str] = {cir.x_oold_iri!r}")
        for f in cir.fields:
            ann = f.py_type
            if f.default_repr is None:
                lines.append(f"    {f.name}: {ann}")
            else:
                ann = f"Optional[{ann}]" if f.default_repr == "None" else ann
                lines.append(f"    {f.name}: {ann} = {f.default_repr}")
        if len(lines) == body_start:  # no members emitted
            lines.append("    pass")
        lines.append("")

    # Rebuild models so self-referential Ref[...] forward refs resolve. This is
    # generated *code*, driven by the IR (not a regex over output text).
    for cir in irs:
        lines.append(f"{cir.name}.model_rebuild()")
    lines.append("")
    return "\n".join(lines)


# Example schema graph + self-check

EXAMPLE_SCHEMAS: Dict[str, dict] = {
    "Item": {
        "title": "Item",
        "x-oold-uuid": "11111111-1111-1111-1111-111111111111",
        "x-oold-iri": "ex:Item",
        "type": "object",
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
    },
    # Alias: same UUID as Item -> must NOT emit a second class; references to
    # it resolve to Item. (Mirrors the generator's UUID-dedup.)
    "Thing": {
        "title": "Thing",
        "x-oold-uuid": "11111111-1111-1111-1111-111111111111",
        "type": "object",
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
    },
    "Named": {
        "title": "Named",
        "x-oold-uuid": "22222222-2222-2222-2222-222222222222",
        "type": "object",
        "properties": {"label": {"type": "string"}},
    },
    # Multiple allOf -> class Person(Item, Named). best_friend is a typed
    # self-referential x-oold-range (legacy bare 'range' also accepted).
    "Person": {
        "title": "Person",
        "x-oold-uuid": "33333333-3333-3333-3333-333333333333",
        "type": "object",
        "allOf": [{"$ref": "Item.json"}, {"$ref": "Named.json"}],
        "properties": {
            "name": {"type": "string"},
            "best_friend": {"type": "string", "x-oold-range": "Person"},
        },
    },
    # References the alias 'Thing' -> resolves to base Item, proving reuse.
    "Widget": {
        "title": "Widget",
        "x-oold-uuid": "44444444-4444-4444-4444-444444444444",
        "type": "object",
        "allOf": [{"$ref": "Thing.json"}],
        "properties": {"watts": {"type": "number"}},
    },
}


def main() -> None:
    irs = build_ir(EXAMPLE_SCHEMAS)
    source = emit(irs)

    print("=" * 70)
    print("GENERATED MODULE")
    print("=" * 70)
    print(source)

    # Execute the generated module and validate the three target properties.
    ns: Dict[str, object] = {}
    exec(compile(source, "<codegen_spike>", "exec"), ns)  # noqa: S102

    Item = ns["Item"]
    Named = ns["Named"]
    Person = ns["Person"]
    Widget = ns["Widget"]
    Ref = ns["Ref"]

    print("=" * 70)
    print("SELF-CHECK")
    print("=" * 70)

    # (1) allOf multiple inheritance
    assert issubclass(Person, Item) and issubclass(Person, Named), Person.__mro__
    print("[ok] allOf -> multiple inheritance: Person(Item, Named)")

    # (2) x-oold-uuid reuse: 'Thing' aliased Item, so no Thing class and Widget
    # inherits the canonical Item.
    assert "Thing" not in ns, "alias 'Thing' must not emit its own class"
    assert issubclass(Widget, Item), "Widget must reuse the canonical Item"
    print("[ok] x-oold-uuid reuse: Thing collapsed into Item; Widget(Item)")

    # (3) typed x-oold-range reference, built from an IRI and lazily typed
    p = Person(id="ex:alice", name="Alice", best_friend="ex:bob")
    assert isinstance(p.best_friend, Ref), type(p.best_friend)
    assert p.best_friend.iri == "ex:bob"
    assert p.model_dump(exclude_none=True)["best_friend"] == "ex:bob"
    print("[ok] x-oold-range -> Ref[Person]; best_friend serialises to IRI")

    # required propagates from the schema (id is required on Item)
    try:
        Person(name="no id")
    except Exception:
        print("[ok] required field 'id' enforced (inherited from Item)")
    else:  # pragma: no cover
        raise AssertionError("expected validation error for missing required id")

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":  # pragma: no cover
    main()
