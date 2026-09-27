"""A discriminated union over the classes an answer may take.

An enum on the class slot and an enum on every other slot constrain them
independently, so a model can pick a class and a unit that cannot occur
together. That is the failure seen in every run of the independent-enum arm:
the class is wrong and the unit belongs to some other class entirely.

A union says what the enum pair cannot. One branch per class, the class slot
pinned with ``const``, and every other slot carrying that class's own values.
Choosing the class then chooses the rest.

Built with ``anyOf`` and not ``oneOf``. No provider profile accepts ``oneOf``;
the OpenAI and Google subsets accept ``anyOf``. Same meaning here, because the
``const`` discriminator already makes the branches mutually exclusive, and one
of them can actually be sent.
"""

from __future__ import annotations

from typing import Any

__all__ = ["branch_for", "flatten_union", "nested_union", "union_schema"]


def branch_for(
    identifier: str,
    properties: dict[str, Any],
    *,
    discriminator: str = "type",
    required: tuple[str, ...] = (),
) -> dict[str, Any]:
    """One branch: this class, and the values it admits.

    ``properties`` holds only what this class narrows. Anything the class does
    not constrain is left to the shared part of the schema, so a branch stays
    the size of the difference rather than a copy of the whole object.
    """
    branch: dict[str, Any] = {
        "type": "object",
        "properties": {discriminator: {"const": identifier}, **properties},
    }
    names = (discriminator, *required)
    branch["required"] = list(dict.fromkeys(names))
    return branch


def union_schema(
    branches: dict[str, dict[str, Any]],
    *,
    discriminator: str = "type",
    required: tuple[str, ...] = (),
    shared: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """An ``anyOf`` over the offered classes.

    ``branches`` maps a class identifier to the properties that class narrows.
    ``shared`` is the part every branch has in common, merged into each one so
    the union stands alone without a ``$ref``, which the strict subsets would
    have to inline anyway.

    Refuses an empty union. A schema with no branch admits nothing, and a model
    asked to satisfy it can only fail, which would read as a finding about the
    model.
    """
    if not branches:
        raise ValueError("a union needs at least one branch, or nothing can satisfy it")

    common = shared or {}
    built = []
    for identifier, narrowed in branches.items():
        merged = {**common, **narrowed}
        built.append(branch_for(identifier, merged, discriminator=discriminator, required=required))
    return {"anyOf": built}


def flatten_union(schema: dict[str, Any], *, discriminator: str = "type") -> dict[str, Any]:
    """Collapse a union into independent enums, losing the pairing.

    What a provider that refuses ``anyOf`` can still be sent. Every branch's
    discriminator value becomes one enum, every other slot's values become the
    union of that slot across branches, and which value went with which class
    is gone. That is a real loss and it is what the degradation measure counts.

    Used by :func:`oold.agent.provider.prepare`. Kept here beside the builder
    so the two stay in step.
    """
    branches = schema.get("anyOf") or schema.get("oneOf") or []
    if not branches:
        return dict(schema)

    identifiers: list[str] = []
    values: dict[str, list[Any]] = {}
    template: dict[str, Any] = {}
    required: list[str] = []

    for branch in branches:
        if not isinstance(branch, dict):
            continue
        properties = branch.get("properties") or {}
        for name in branch.get("required") or ():
            if name not in required:
                required.append(name)
        for name, definition in properties.items():
            if not isinstance(definition, dict):
                continue
            if name == discriminator:
                const = definition.get("const")
                if const is not None and const not in identifiers:
                    identifiers.append(const)
                for member in definition.get("enum") or ():
                    if member not in identifiers:
                        identifiers.append(member)
                continue
            template.setdefault(name, {k: v for k, v in definition.items() if k != "enum"})
            for member in definition.get("enum") or ():
                bucket = values.setdefault(name, [])
                if member not in bucket:
                    bucket.append(member)

    properties: dict[str, Any] = {}
    if identifiers:
        properties[discriminator] = {"type": "string", "enum": identifiers}
    for name, definition in template.items():
        merged = dict(definition)
        if name in values:
            merged["enum"] = values[name]
        properties[name] = merged

    flattened = {"type": "object", "properties": properties}
    if required:
        flattened["required"] = required
    return flattened


def nested_union(
    branches: dict[str, dict[str, Any]],
    parents: dict[str, tuple[str, ...]],
    *,
    discriminator: str = "type",
    shared: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A union shaped like the class hierarchy instead of flattened over it.

    A flat union repeats every inherited property in every branch. Measured on
    the schema.org pool that is 3,047 property slots against the 851 the
    classes actually declare, a 3.6x duplication, and it throws away the one
    thing the hierarchy states: that a Book is a CreativeWork, so whatever is
    true of a CreativeWork is already true of it.

    Nesting says it once. Each node carries what that class declares, and its
    subclasses hang beneath it as a further choice. A sibling ``properties``
    and ``anyOf`` are conjoined by JSON Schema, so this needs no ``allOf``,
    which every strict provider subset rejects.

    Multiple inheritance does not survive. 48 of 906 schema.org classes name
    two parents or three, and a tree can hold one, so the first is used and
    the rest are lost. That loss is real and belongs in the record beside the
    result, not hidden here.
    """
    if not branches:
        raise ValueError("a union needs at least one branch, or nothing can satisfy it")

    children: dict[str, list[str]] = {}
    roots: list[str] = []
    for name in branches:
        first = next((p for p in parents.get(name, ()) if p in branches), None)
        if first is None:
            roots.append(name)
        else:
            children.setdefault(first, []).append(name)

    def node(name: str) -> dict[str, Any]:
        built: dict[str, Any] = {
            "type": "object",
            "properties": {discriminator: {"const": name}, **branches[name]},
            "required": [discriminator],
        }
        below = children.get(name) or []
        if not below:
            return built
        # This class itself, or any of its subclasses. The self branch repeats
        # the discriminator only, because the properties above already apply.
        built["anyOf"] = [
            {"properties": {discriminator: {"const": name}}},
            *[node(child) for child in below],
        ]
        built["properties"] = {k: v for k, v in built["properties"].items() if k != discriminator}
        built["properties"][discriminator] = {
            "enum": [name, *_descendants(name, children)],
        }
        return built

    top = [node(name) for name in roots]
    if len(top) == 1 and not shared:
        return top[0]
    return {"anyOf": top, **({"properties": shared} if shared else {})}


def _descendants(name: str, children: dict[str, list[str]]) -> list[str]:
    out: list[str] = []
    for child in children.get(name) or []:
        out.append(child)
        out.extend(_descendants(child, children))
    return out
