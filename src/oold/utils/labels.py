"""Harvesting human-readable labels for the ontology IRIs a schema maps to.

Several widely used ontologies mint opaque identifiers: EMMO mints
``EMMO_c1c8ac3c_8a1c_4777_8e0b_14c1f9f9b0c6``, OBO mints ``OBI_0001937``. Showing those raw is
unreadable, and looking each one up by hand does not scale.

Reading pinned snapshots instead of querying a service keeps a build offline and
deterministic, and makes refreshing labels a deliberate act tied to an ontology version bump.
Which snapshots to read is the caller's: they are pinned per project and are not something this
library can know.

Only the IRIs the schemas actually map are kept. A snapshot carries tens of thousands of
labels, and keeping them all would bury the handful a document shows in a megabyte that changes
whenever an ontology is repinned.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

#: prefLabel wins over label, English preferred, blank nodes skipped.
LABEL_QUERY = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?term ?label WHERE {
  { ?term skos:prefLabel ?label } UNION { ?term rdfs:label ?label }
  FILTER (isIRI(?term))
  FILTER (!bound(?label) || lang(?label) IN ("", "en"))
}
ORDER BY ?term DESC(?label)
"""

#: Lookup service for an IRI no pinned snapshot carries.
OLS_TERMS = "https://www.ebi.ac.uk/ols4/api/terms?iri="

#: Suffixes read as ontology documents when a directory is given.
ONTOLOGY_SUFFIXES = (".ttl", ".owl")


def mapped_iris(schemas: Iterable[dict[str, Any]]) -> set[str]:
    """Every IRI the given schemas map to, compact forms expanded with their own prefixes.

    Read from the schemas rather than listed anywhere. A list would drift the moment a mapping
    is added, and it would drift silently: the only symptom is an unlabelled row.
    """
    prefixes: dict[str, str] = {}
    contexts: list[dict[str, Any]] = []
    synonyms: list[dict[str, Any]] = []
    for schema in schemas:
        context = schema.get("@context")
        parts = [part for part in context if isinstance(part, dict)] if isinstance(context, list) else [context]
        for part in parts:
            if isinstance(part, dict):
                contexts.append(part)
                prefixes.update({k: v for k, v in part.items() if isinstance(v, str) and v.endswith(("#", "/", ":"))})
        synonyms.append(schema.get("x-oold-context") or {})

    found: set[str] = set()

    def add(iri: Any) -> None:
        # A prefix declaration is a namespace, not a term, and nothing can label it.
        if not isinstance(iri, str) or iri.startswith("@") or iri.endswith(("#", "/", ":")):
            return
        if iri.startswith(("http://", "https://")):
            found.add(iri)
            return
        prefix, _, rest = iri.partition(":")
        if prefix in prefixes and rest:
            found.add(prefixes[prefix] + rest)

    for part in contexts:
        for value in part.values():
            add(value.get("@id") if isinstance(value, dict) else value)
    for block in synonyms:
        for entries in block.values():
            for iri in entries or {}:
                add(iri)
    return found


def ontology_iri(graph: Any) -> str:
    """The IRI of the ontology a document defines, for attributing a label to its owner."""
    from rdflib import OWL, RDF

    for subject in graph.subjects(RDF.type, OWL.Ontology):
        return str(subject)
    return ""


def harvest(path: Path) -> tuple[dict[str, str], str]:
    """Every labelled subject in one ontology document, and that document's own IRI.

    Parsed rather than pattern-matched: a Turtle document has multi-line strings, escapes and
    prefix scoping, and a regex over it drops terms whose comment happens to contain a line
    starting at column zero, without saying so.
    """
    from rdflib import Graph

    graph = Graph()
    graph.parse(str(path), format="xml" if path.suffix == ".owl" else "turtle")
    found: dict[str, str] = {}
    for row in graph.query(LABEL_QUERY):
        iri = str(row.term)
        if iri.startswith(("http://", "https://")):
            found.setdefault(iri, str(row.label))
    return found, ontology_iri(graph)


def iri_prefix(ontology: str) -> str:
    """The namespace an ontology IRI covers, so a term can be matched to its owner.

    A build that leaves its version placeholder unsubstituted, as QUDT does with
    ``$$QUDT_VERSION$$``, would otherwise cover nothing and let whichever importing document
    sorts first claim its terms.
    """
    if not ontology:
        return ""
    parts = [part for part in ontology.rstrip("/").split("/") if not part.startswith("$$")]
    return "/".join(parts[:-1]) + "/"


def owns(ontology: str, term: str) -> bool:
    """Whether an ontology is the one that defines a term.

    Namespace alone cannot decide it: every OBO ontology mints under
    ``purl.obolibrary.org/obo/``, so a document that merely imports UO covers its terms as well
    as UO does. Where a local name carries its ontology as a prefix, ``UO_0000010`` or
    ``EMMO_c1c8...``, that prefix decides; otherwise the namespace does.
    """
    if not ontology:
        return False
    short = ontology.rstrip("/").rsplit("/", 1)[-1].removesuffix(".owl").removesuffix(".ttl").lower()
    local = term.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    if "_" in local:
        return local.split("_")[0].lower() == short
    return term.startswith(iri_prefix(ontology))


def ontology_files(source: Path) -> list[Path]:
    """The ontology documents a path stands for: itself, or everything under a directory."""
    if source.is_dir():
        return sorted(path for path in source.rglob("*") if path.suffix in ONTOLOGY_SUFFIXES)
    return [source]


def harvest_all(
    sources: Sequence[Path],
    source_name: Callable[[Path, Path], str] | None = None,
    on_error: Callable[[Path, Exception], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Labels from every snapshot, preferring the document that owns each term.

    An ontology that imports another carries its labels too, so a term is labelled by the
    ontology whose own IRI covers it rather than by a domain ontology that happens to include
    it. ``source_name`` names the provenance recorded per label; it receives the source that was
    given and the file within it, and defaults to the file name.
    """
    labels: dict[str, dict[str, Any]] = {}
    for source in sources:
        for path in ontology_files(source):
            try:
                found, ontology = harvest(path)
            except Exception as exc:
                if on_error is not None:
                    on_error(path, exc)
                continue
            name = source_name(source, path) if source_name else path.name
            for iri, label in found.items():
                mine = owns(ontology, iri)
                if iri not in labels or (mine and not labels[iri].get("owner")):
                    labels[iri] = {"label": label, "source": name, "owner": mine}
    return labels


def resolve_missing(
    iris: Iterable[str],
    endpoint: str = OLS_TERMS,
    timeout: float = 30.0,
    on_error: Callable[[str, Exception | None], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Labels for IRIs no pinned snapshot carries, looked up over the network.

    Separate from :func:`harvest_all` because it is the one step that is neither offline nor
    reproducible: a caller opts into it, and what it returns should be committed so the next
    build does not need it.
    """
    found: dict[str, dict[str, Any]] = {}
    for iri in sorted(iris):
        try:
            with urllib.request.urlopen(endpoint + urllib.parse.quote(iri, safe=""), timeout=timeout) as response:  # noqa: S310
                terms = json.load(response).get("_embedded", {}).get("terms", [])
            if not terms:
                if on_error is not None:
                    on_error(iri, None)
                continue
            found[iri] = {"label": terms[0]["label"], "source": "ols4"}
        except Exception as exc:
            if on_error is not None:
                on_error(iri, exc)
    return found


def label_map(
    labels: dict[str, dict[str, Any]],
    wanted: Iterable[str],
    skip_prefix: str | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """The harvested labels narrowed to the IRIs that are mapped, plus the ones still missing.

    ``skip_prefix`` names a namespace whose terms have no ontology label to find, typically the
    library's own placeholders: those are described by the schema that mints them, so their
    absence is not a gap. ``owner`` is dropped, having only served to choose between two
    documents claiming the same term.
    """
    wanted = set(wanted)
    kept = {
        iri: {key: value for key, value in entry.items() if key != "owner"}
        for iri, entry in sorted(labels.items())
        if iri in wanted
    }
    missing = sorted(iri for iri in wanted - set(kept) if skip_prefix is None or not iri.startswith(skip_prefix))
    return kept, missing
