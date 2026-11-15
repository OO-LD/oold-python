"""Bundling the mappings carried by schemas into SSSOM mapping sets.

A schema states its correspondences inline: one consensus mapping per term in ``@context``, and
any number of community synonyms in ``x-oold-context``, each tagged with the set it belongs to.
That is the right place to author a mapping, because a mapping is only meaningful next to the
term it maps. It is the wrong place to consume one: a tool asking "everything this community
says about this library" would have to walk every schema and filter.

So the sets are derived rather than maintained. This collects the inline mappings, groups them
by ``mapping_set_id`` and renders one SSSOM TSV per set. The consensus mappings are emitted as
a set of their own, so the reading an instance has with nothing selected is described in the
same form as the alternatives to it.

SSSOM specifies TSV with a commented YAML preamble, which is what is rendered here. Nothing
writes a file: the caller decides where a set goes, since that path is also what its
``mapping_set_id`` has to name.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from oold.utils.mappings import context_of, set_name

#: SSSOM columns written, in order.
COLUMNS = (
    "subject_id",
    "subject_label",
    "predicate_id",
    "object_id",
    "object_label",
    "mapping_justification",
    "subject_source",
    "subject_source_version",
    "object_source",
    "object_source_version",
    "comment",
)

EXACT = "skos:exactMatch"

#: How a mapping predicate reads in the other direction, for chaining.
INVERSE = {
    "skos:exactMatch": "skos:exactMatch",
    "skos:closeMatch": "skos:closeMatch",
    "skos:relatedMatch": "skos:relatedMatch",
    "skos:broadMatch": "skos:narrowMatch",
    "skos:narrowMatch": "skos:broadMatch",
}

#: Namespaces every generated set needs, whatever the schemas declare.
BUILTIN_CURIES = {
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "semapv": "https://w3id.org/semapv/vocab/",
}

CURATED = "semapv:ManualMappingCuration"
CHAINED = "semapv:MappingChaining"

#: Name of the set holding the mappings a schema states in its own ``@context``.
CONSENSUS = "consensus"


@dataclass(frozen=True)
class SchemaGroup:
    """Schemas that share one subject source: a module, a package, a release.

    ``subject_source`` identifies what the terms belong to and goes in the SSSOM column of that
    name. It carries no version, because a term keeps its identity across releases and the
    version has a column of its own.
    """

    subject_source: str
    subject_source_version: str = ""
    schemas: Sequence[dict[str, Any]] = field(default_factory=tuple)


def prefixes(context: dict[str, Any]) -> dict[str, str]:
    """The namespaces a context declares, in both forms it may declare them.

    A schema usually declares its own namespace as a term definition carrying ``@prefix``
    rather than as a plain string, and those are exactly the namespaces its placeholder terms
    live in: reading only the string form leaves every one of its own terms unexpandable.
    """
    out: dict[str, str] = {}
    for term, definition in context.items():
        if term.startswith("@") or not term.isalnum():
            continue
        if isinstance(definition, str):
            target_iri, declared = definition, False
        elif isinstance(definition, dict):
            target_iri, declared = definition.get("@id"), bool(definition.get("@prefix"))
        else:
            continue
        if isinstance(target_iri, str) and (declared or target_iri.endswith(("#", "/", ":"))):
            out[term] = target_iri
    return out


def expand(iri: str, curie_map: dict[str, str]) -> str:
    """The absolute form of a CURIE, or the input where no prefix applies."""
    if not isinstance(iri, str) or ":" not in iri or iri.startswith(("http://", "https://")):
        return iri
    prefix, rest = iri.split(":", 1)
    return curie_map[prefix] + rest if prefix in curie_map else iri


def target(definition: Any) -> str | None:
    """The IRI a ``@context`` term maps to, ignoring the keyword aliases."""
    iri = definition.get("@id") if isinstance(definition, dict) else definition
    return iri if isinstance(iri, str) and not iri.startswith("@") else None


def compose(left: str, right: str) -> str | None:
    """The predicate of a chain, or ``None`` when the chain proves nothing.

    Only a chain with an exact link on at least one side survives. Two close matches do not
    compose: "roughly the same as X" and "X is roughly the same as Y" says nothing reliable
    about Y, and a mapping commons that grades a guess like a curation is worse than one with
    fewer rows.
    """
    if left == EXACT:
        return right
    if right == EXACT:
        return left
    return None


def strip_version(iri: str, own_prefix: str, version_index: int | None = 1) -> str:
    """Drop the version segment from an identity IRI minted under ``own_prefix``.

    A term keeps its identity across releases, and the version has its own SSSOM column.
    Leaving it in the IRI would make one term look like two whenever a set from an earlier
    release is merged with a later one.
    """
    if version_index is None or not iri.startswith(own_prefix):
        return iri
    parts = iri[len(own_prefix) :].split("/")
    if len(parts) <= version_index + 1:
        return iri
    del parts[version_index]
    return own_prefix + "/".join(parts)


def collect(
    groups: Iterable[SchemaGroup],
    own_prefix: str | None = None,
    version_index: int | None = 1,
    labels: dict[str, Any] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """Every mapping the given schemas carry, grouped by mapping set.

    Returns the sets keyed by name, and the CURIE map assembled from the contexts, which the
    rows are written against and the preamble has to declare.
    """
    sets: dict[str, list[dict[str, Any]]] = {}
    curie_map: dict[str, str] = {}
    label_map = labels or {}

    for group in groups:
        merged: dict[str, Any] = {}
        for schema in group.schemas:
            merged.update(context_of(schema))
        curie_map.update(prefixes(merged))

        def row(term, subject, predicate, obj, comment="", source="", version="", group=group):
            entry = label_map.get(expand(obj, curie_map)) or {}
            return {
                "subject_id": subject,
                "subject_label": term,
                "predicate_id": predicate,
                "object_id": obj,
                "object_label": entry.get("label", "") if isinstance(entry, dict) else str(entry),
                "mapping_justification": CURATED,
                "subject_source": group.subject_source,
                "subject_source_version": group.subject_source_version,
                "object_source": source,
                "object_source_version": version,
                "comment": comment,
            }

        def subject_of(context, term, group=group):
            """What a row is about.

            A term name alone does not identify a term: two schemas of one group may spell the
            same key and mean different edges, and joining their mappings on the name would
            chain two communities through a term neither of them shares. Where the term maps to
            a placeholder of this library, that placeholder is the identity, since it belongs
            to exactly one schema.
            """
            iri = expand(target(context.get(term)) or "", curie_map)
            if own_prefix is None or not iri.startswith(own_prefix):
                return f"{group.subject_source}#{term}"
            return strip_version(iri, own_prefix, version_index)

        for schema in group.schemas:
            context = context_of(schema)
            for term, definition in context.items():
                iri = target(definition)
                if iri and not iri.endswith(("#", "/", ":")):
                    subject = subject_of(context, term)
                    # A placeholder is its own subject, and stating that it matches itself
                    # would say nothing.
                    if expand(iri, curie_map) != subject:
                        sets.setdefault(CONSENSUS, []).append(row(term, subject, EXACT, iri))
            for term, synonyms in (schema.get("x-oold-context") or {}).items():
                for iri, fragment in (synonyms or {}).items():
                    if not isinstance(fragment, dict):
                        continue
                    meta = fragment.get("x-oold-sssom") or {}
                    set_id = meta.get("mapping_set_id")
                    if not set_id:
                        continue
                    sets.setdefault(set_name(set_id), []).append(
                        row(
                            term,
                            subject_of(context, term),
                            meta.get("predicate_id", EXACT),
                            iri,
                            meta.get("comment", ""),
                            meta.get("object_source", ""),
                            meta.get("object_source_version", ""),
                        )
                    )
    return sets, curie_map


def crosswalk(
    left_name: str,
    left_rows: Sequence[dict[str, Any]],
    right_name: str,
    right_rows: Sequence[dict[str, Any]],
    curie_map: dict[str, str],
    source_of: Any = None,
) -> list[dict[str, Any]]:
    """Mappings between two communities, chained through the terms they both map.

    Chaining two curated mappings through the term they share gives a mapping between two
    communities that nobody authored. It is worth publishing, and worth keeping apart from what
    was curated, which is what the chaining justification records.

    ``source_of`` turns a set name into the IRI of the set it came from; without it the
    provenance columns are left empty.
    """
    by_term: dict[str, list[dict[str, Any]]] = {}
    for row in right_rows:
        by_term.setdefault(row["subject_id"], []).append(row)

    def source(name: str) -> str:
        return source_of(name) if source_of is not None else ""

    out: list[dict[str, Any]] = []
    for left in left_rows:
        for right in by_term.get(left["subject_id"], []):
            if left["object_id"] == right["object_id"]:
                continue
            predicate = compose(INVERSE.get(left["predicate_id"], left["predicate_id"]), right["predicate_id"])
            if not predicate:
                continue
            out.append({
                "subject_id": expand(left["object_id"], curie_map),
                "subject_label": left["object_label"],
                "predicate_id": predicate,
                "object_id": expand(right["object_id"], curie_map),
                "object_label": right["object_label"],
                "mapping_justification": CHAINED,
                "subject_source": source(left_name),
                "subject_source_version": left.get("object_source_version", ""),
                "object_source": source(right_name),
                "object_source_version": right["object_source_version"],
                "comment": f"chained through {left['subject_label']}",
            })
    return out


def render_set(
    name: str,
    rows: Sequence[dict[str, Any]],
    curie_map: dict[str, str],
    set_id: str,
    version: str = "dev",
    title: str | None = None,
    license: str | None = None,
    provider: str | None = None,
    comment: str | None = None,
) -> str:
    """One SSSOM set as text: the commented YAML preamble, the header row, then the mappings.

    Only the prefixes the rows actually use are declared, and the rows are sorted, so a
    regenerated set is byte-identical unless a mapping changed.
    """
    used = sorted({
        iri.split(":", 1)[0]
        for row in rows
        for iri in (row["object_id"], row["predicate_id"], row["mapping_justification"])
        if ":" in iri and not iri.startswith("http")
    })
    known = {**BUILTIN_CURIES, **curie_map}

    preamble = [
        f"# mapping_set_id: {set_id}",
        f"# mapping_set_version: {version}",
        f"# mapping_set_title: {title or name}",
        *([f"# comment: {comment}"] if comment else []),
        *([f"# license: {license}"] if license else []),
        *([f"# mapping_provider: {provider}"] if provider else []),
        "# curie_map:",
    ]
    preamble += [f"#   {prefix}: {known[prefix]}" for prefix in used if prefix in known]

    lines = [*preamble, "\t".join(COLUMNS)]
    for row in sorted(rows, key=lambda entry: (entry["subject_label"], entry["object_id"])):
        lines.append("\t".join(str(row[column]).replace("\t", " ") for column in COLUMNS))
    return "\n".join(lines) + "\n"
