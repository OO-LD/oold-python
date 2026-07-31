"""Detection of cyclic scoped ``@context`` references.

Ports ``validate.mjs`` lines 195-227. This module *detects*; it does not resolve. Context
resolution lives in :mod:`~oold.validation.context_resolution` and the pyld document loader.

A schema's ``@context`` can reference other schema files, both as a parent context and as a
term's scoped context. When those references form a cycle - a value type whose scoped context
embeds itself, or two types embedding each other - a JSON-LD processor is required to eagerly
validate the recursive scoped context. The specification bounds that recursion (validate scoped
context = false, plus context overflow), but neither mainstream processor honours the bound:
jsonld.js exhausts the heap and PyLD raises ``RecursionError``. Such a schema therefore cannot
be round-tripped in practice by either toolchain.

So the affected schemas are identified up front and their round-trip and remote-context checks
are skipped with a warning, rather than crashing the run. Every other check still applies to
them, and ``$ref`` resolution is unaffected.

A self-reference through the *top-level* context, with no scoped ``@context`` involved, is not a
cycle here and round-trips fine.
"""

from __future__ import annotations

from typing import Any

#: Marks a string inside a ``@context`` as a reference to another OO-LD schema.
SCHEMA_SUFFIX = ".schema.json"


def context_file_refs(context: Any, out: set[str] | None = None) -> set[str]:
    """Every schema file referenced anywhere inside a ``@context`` value.

    Both parent contexts and terms' scoped contexts are collected, since both are plain string
    references to a schema file. ``x-oold-range`` references are correctly excluded: they live
    in ``properties``, not in ``@context``, and load no context.
    """
    if out is None:
        out = set()
    if isinstance(context, str):
        if context.endswith(SCHEMA_SUFFIX):
            out.add(context)
        return out
    if isinstance(context, list):
        for entry in context:
            context_file_refs(entry, out)
        return out
    if isinstance(context, dict):
        for value in context.values():
            context_file_refs(value, out)
    return out


def build_graph(schemas: dict[str, Any]) -> dict[str, list[str]]:
    """Map each schema file name to the schema files its ``@context`` references.

    ``schemas`` is keyed by file name, as the checks operate on a directory of schemas. A
    document that cannot be read contributes an empty edge list rather than aborting, matching
    the reference harness.
    """
    graph: dict[str, list[str]] = {}
    for name, document in schemas.items():
        if isinstance(document, dict):
            graph[name] = sorted(context_file_refs(document.get("@context")))
        else:
            graph[name] = []
    return graph


def reaches_cycle(graph: dict[str, list[str]]) -> set[str]:
    """Every node that lies on, or can reach, a cycle in the context-reference graph."""
    WHITE, GREY, BLACK = None, 1, 2
    color: dict[str, Any] = {}
    on_cycle: set[str] = set()

    def visit(node: str, stack: list[str]) -> None:
        color[node] = GREY
        for neighbour in graph.get(node, []):
            if neighbour not in graph:
                # A reference outside the set under consideration; not a cycle we can see.
                continue
            if color.get(neighbour) == GREY:
                # Back edge: everything from the neighbour onwards in the stack is on a cycle.
                index = stack.index(neighbour) if neighbour in stack else 0
                for entry in stack[max(index, 0) :]:
                    on_cycle.add(entry)
                on_cycle.add(neighbour)
            elif color.get(neighbour, WHITE) is WHITE:
                visit(neighbour, [*stack, neighbour])
        color[node] = BLACK

    for name in graph:
        if color.get(name, WHITE) is WHITE:
            visit(name, [name])

    # Propagate backwards: a schema that references a cyclic one inherits the problem, because
    # loading its context eventually loads the cycle.
    reaches = set(on_cycle)
    changed = True
    while changed:
        changed = False
        for name, neighbours in graph.items():
            if name not in reaches and any(n in reaches for n in neighbours):
                reaches.add(name)
                changed = True
    return reaches


def cyclic_scoped_contexts(schemas: dict[str, Any]) -> set[str]:
    """Schema file names whose context chain reaches a cycle. The convenience entry point."""
    return reaches_cycle(build_graph(schemas))
