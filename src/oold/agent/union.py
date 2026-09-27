"""A discriminated union over the classes an answer may take.

An enum on the class slot and an enum on every other slot constrain them
independently, so a model can pick a class and a unit that cannot occur
together. That is the failure seen in every run of the independent-enum arm:
the class is wrong and the unit belongs to some other class entirely.

A union says what the enum pair cannot. One branch per class, the class slot
pinned with ``const``, and every other slot carrying that class's own values.
Choosing the class then chooses the rest.

Built with ``anyOf`` and not ``oneOf``. No provider profile accepts ``oneOf``, but
the OpenAI and Google subsets accept ``anyOf``. Same meaning here, because the
``const`` discriminator already makes the branches mutually exclusive, and one
of them can actually be sent.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

__all__ = ["branch_for", "flatten_union", "hierarchy_union", "union_schema"]


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
    is gone. That is a real loss and the degradation measure counts it.

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


def hierarchy_union(
    branches: dict[str, dict[str, Any]],
    parents: dict[str, tuple[str, ...]],
    *,
    discriminator: str = "type",
    concrete: Collection[str] | None = None,
) -> dict[str, Any]:
    """A union over classes that inherit, stated once each.

    Each class becomes a ``$defs`` entry holding what it declares and an
    ``allOf`` of its parents, so a property is written where it is declared and
    referenced everywhere it is inherited. The choice is a flat ``anyOf`` over
    the classes an answer may take.

    ``allOf`` is used here instead of a tree. A tree holds one parent, and 48 of
    906 schema.org classes name two or three: ``LocalBusiness`` is both an
    ``Organization`` and a ``Place``. An ``allOf`` holds both, and it degrades
    the right way. A provider that rejects combinators merges it, and merging
    an intersection of objects is exactly the property union that inheritance
    means, so nothing is lost. Flattening an ``anyOf`` loses the discrimination
    and that is a real loss, the asymmetry the degradation measure
    reports.

    ``concrete`` names the classes an answer may actually be. Left out, every
    class is offered, which is right when the catalogue is the answer space and
    wrong when the catalogue includes abstract ancestors carried only to hold
    shared properties.
    """
    if not branches:
        raise ValueError("a union needs at least one branch, or nothing can satisfy it")

    defs: dict[str, Any] = {}
    for name, own in branches.items():
        entry: dict[str, Any] = {"type": "object", "properties": dict(own)}
        # Every ancestor, not only the direct parents. A chain of references is
        # the tidier schema and the transform does not survive it: inlining
        # treats the second hop as recursion and cuts it, so a grandparent's
        # properties never arrive. Referencing the whole ancestry keeps every
        # merge one hop deep, which the transform does handle.
        inherited = [a for a in _ancestry(name, parents) if a in branches]
        if inherited:
            entry["allOf"] = [{"$ref": f"#/$defs/{a}"} for a in inherited]
        defs[name] = entry

    offered = [name for name in branches if concrete is None or name in concrete]
    if not offered:
        raise ValueError("no offered class is concrete, so the union would admit nothing")

    return {
        "$defs": defs,
        "anyOf": [
            {
                "type": "object",
                "properties": {discriminator: {"const": name}},
                "required": [discriminator],
                "allOf": [{"$ref": f"#/$defs/{name}"}],
            }
            for name in offered
        ],
    }


def _ancestry(name: str, parents: dict[str, tuple[str, ...]]) -> list[str]:
    """Every ancestor of a class, nearest first, each named once.

    Breadth first, so a class that inherits from two parents keeps the order
    the schema declares them in and a shared grandparent appears once.
    """
    seen: list[str] = []
    queue = list(parents.get(name, ()))
    while queue:
        current = queue.pop(0)
        if current in seen or current == name:
            continue
        seen.append(current)
        queue.extend(parents.get(current, ()))
    return seen
