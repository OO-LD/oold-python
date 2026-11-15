"""Harvesting labels for the ontology IRIs a schema maps to.

What matters here is which terms are wanted and which document gets to name them: an ontology
that imports another carries its labels too, so namespace alone decides it wrongly.
"""

import json
from pathlib import Path

import pytest

from oold.utils.labels import (
    harvest,
    harvest_all,
    iri_prefix,
    label_map,
    mapped_iris,
    ontology_files,
    owns,
    resolve_missing,
)

EMMO = "https://w3id.org/emmo#EMMO_c1c8ac3c"
UO = "http://purl.obolibrary.org/obo/UO_0000010"

SCHEMA = {
    "@context": {
        "emmo": "https://w3id.org/emmo#",
        "obo": "http://purl.obolibrary.org/obo/",
        "name": "emmo:EMMO_c1c8ac3c",
        "typed": {"@id": "obo:UO_0000010"},
        "absolute": "https://vocab.example/term",
    },
    "x-oold-context": {"name": {"obo:IAO_0000039": {"x-oold-sssom": {"mapping_set_id": "s"}}}},
}


def test_mapped_iris_expands_a_curie_with_the_schemas_own_prefixes():
    found = mapped_iris([SCHEMA])
    assert EMMO in found
    assert UO in found
    assert "https://vocab.example/term" in found
    assert "http://purl.obolibrary.org/obo/IAO_0000039" in found


def test_mapped_iris_ignores_prefix_declarations_and_keyword_aliases():
    """A namespace is not a term, and nothing can label it."""
    schema = {"@context": {"emmo": "https://w3id.org/emmo#", "id": "@id", "type": "@type"}}
    assert mapped_iris([schema]) == set()


def test_mapped_iris_merges_a_list_context():
    schema = {"@context": ["Remote.schema.json", {"ex": "https://e.example/"}, {"a": "ex:a"}]}
    assert mapped_iris([schema]) == {"https://e.example/a"}


def test_mapped_iris_drops_a_curie_whose_prefix_is_undeclared():
    assert mapped_iris([{"@context": {"a": "unknown:thing"}}]) == set()


@pytest.mark.parametrize(
    ("ontology", "term", "expected"),
    [
        ("http://purl.obolibrary.org/obo/uo.owl", UO, True),
        # every OBO ontology mints in one namespace, so an importer must not claim the term
        ("http://purl.obolibrary.org/obo/obi.owl", UO, False),
        ("https://vocab.example/thing", "https://vocab.example/term", True),
        ("", UO, False),
    ],
)
def test_owns_prefers_the_local_name_prefix_over_the_namespace(ontology, term, expected):
    assert owns(ontology, term) is expected


def test_iri_prefix_skips_an_unsubstituted_version_placeholder():
    assert iri_prefix("http://qudt.org/$$QUDT_VERSION$$/vocab/unit") == "http://qudt.org/vocab/"
    assert iri_prefix("") == ""


def test_ontology_files_reads_a_directory_or_a_single_document(tmp_path):
    (tmp_path / "a.ttl").write_text("", encoding="utf-8")
    (tmp_path / "b.owl").write_text("", encoding="utf-8")
    (tmp_path / "notes.md").write_text("", encoding="utf-8")
    assert [p.name for p in ontology_files(tmp_path)] == ["a.ttl", "b.owl"]
    assert ontology_files(tmp_path / "a.ttl") == [tmp_path / "a.ttl"]


def _turtle(path: Path, ontology: str, terms: dict) -> Path:
    lines = [
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        f"<{ontology}> a owl:Ontology .",
    ]
    lines += [f'<{iri}> rdfs:label "{label}" .' for iri, label in terms.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_harvest_returns_the_labels_and_the_documents_own_iri(tmp_path):
    path = _turtle(tmp_path / "uo.ttl", "http://purl.obolibrary.org/obo/uo", {UO: "metre"})
    found, ontology = harvest(path)
    assert found[UO] == "metre"
    assert ontology == "http://purl.obolibrary.org/obo/uo"


def test_harvest_all_prefers_the_document_that_owns_the_term(tmp_path):
    importer = tmp_path / "obi"
    owner = tmp_path / "uo"
    importer.mkdir()
    owner.mkdir()
    _turtle(importer / "obi.ttl", "http://purl.obolibrary.org/obo/obi", {UO: "from the importer"})
    _turtle(owner / "uo.ttl", "http://purl.obolibrary.org/obo/uo", {UO: "from the owner"})

    labels = harvest_all([importer, owner])
    assert labels[UO]["label"] == "from the owner"

    # and the other way round, so it is ownership deciding and not the order
    labels = harvest_all([owner, importer])
    assert labels[UO]["label"] == "from the owner"


def test_harvest_all_reports_an_unreadable_snapshot_and_continues(tmp_path):
    broken = tmp_path / "broken.ttl"
    broken.write_text("this is not turtle <<<", encoding="utf-8")
    good = _turtle(tmp_path / "uo.ttl", "http://purl.obolibrary.org/obo/uo", {UO: "metre"})
    seen = []
    labels = harvest_all([broken, good], on_error=lambda path, exc: seen.append(path.name))
    assert seen == ["broken.ttl"]
    assert labels[UO]["label"] == "metre"


def test_label_map_keeps_only_the_mapped_iris_and_drops_the_owner_flag():
    harvested = {UO: {"label": "metre", "source": "uo.ttl", "owner": True}, EMMO: {"label": "x", "source": "e.ttl"}}
    kept, missing = label_map(harvested, {UO})
    assert kept == {UO: {"label": "metre", "source": "uo.ttl"}}
    assert missing == []


def test_label_map_reports_a_mapped_iri_no_snapshot_carries():
    kept, missing = label_map({}, {UO, EMMO})
    assert kept == {}
    assert missing == sorted([UO, EMMO])


def test_label_map_does_not_report_the_libraries_own_placeholders_as_missing():
    """A placeholder is described by the schema that mints it, so there is no label to find."""
    own = "https://w3id.org/oo-ld/schemas/materials/0.2/Thing.schema.json"
    _, missing = label_map({}, {own, UO}, skip_prefix="https://w3id.org/oo-ld/schemas/")
    assert missing == [UO]


class _Response:
    """Minimal stand-in for what urlopen returns, so the lookup is exercised without a network."""

    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_resolve_missing_reads_the_label_a_lookup_service_returns(monkeypatch):
    seen = []

    def urlopen(url, timeout=None):
        seen.append(url)
        return _Response({"_embedded": {"terms": [{"label": "metre"}]}})

    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    found = resolve_missing([UO], endpoint="https://lookup.example/terms?iri=")

    assert found == {UO: {"label": "metre", "source": "ols4"}}
    assert seen == ["https://lookup.example/terms?iri=http%3A%2F%2Fpurl.obolibrary.org%2Fobo%2FUO_0000010"]


def test_resolve_missing_reports_an_iri_the_service_does_not_know(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout=None: _Response({"_embedded": {"terms": []}}))
    seen = []

    assert resolve_missing([UO], on_error=lambda iri, exc: seen.append((iri, exc))) == {}
    assert seen == [(UO, None)]


def test_resolve_missing_reports_an_unreachable_service_rather_than_raising(monkeypatch):
    def urlopen(url, timeout=None):
        raise OSError("no route to host")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    seen = []

    assert resolve_missing([UO, EMMO], on_error=lambda iri, exc: seen.append(iri)) == {}
    assert seen == sorted([UO, EMMO])


def test_ontology_iri_is_empty_for_a_document_that_declares_none(tmp_path):
    path = tmp_path / "terms.ttl"
    path.write_text('<http://x.example/a> <http://www.w3.org/2000/01/rdf-schema#label> "a" .\n', encoding="utf-8")
    found, ontology = harvest(path)
    assert ontology == ""
    assert found["http://x.example/a"] == "a"
