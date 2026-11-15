"""Every mapping set read back, not just the declared one.

The rest of the suite exercises the context a schema declares. These pin the part that is
otherwise unproved: that selecting a set still returns the document it started from, and that a
set which loses something says so.
"""

from oold.validation.effective_views import (
    CHECK_ID,
    View,
    canonical,
    effective_context,
    effective_views,
    undefined_terms,
    view_checks,
)

SET_A = "https://example.org/sets/a.sssom.tsv"
SET_B = "https://example.org/sets/b.sssom.tsv"

BASE = {
    "@context": {
        "ex": "https://example.org/",
        "other": "https://other.example/",
        "type": "@type",
        "id": "@id",
        "name": "ex:name",
        "size": {"@id": "ex:size", "@type": "http://www.w3.org/2001/XMLSchema#double"},
    },
    "x-oold-context": {
        "name": {"other:label": {"x-oold-sssom": {"mapping_set_id": SET_A}}},
        "size": {
            "other:extent": {
                "@type": "http://www.w3.org/2001/XMLSchema#double",
                "x-oold-sssom": {"mapping_set_id": SET_B},
            }
        },
    },
}

INSTANCE = {"@id": "https://example.org/thing", "type": "ex:Thing", "name": "a name", "size": 2.5}


def test_the_consensus_reading_comes_first_and_every_declared_set_follows():
    views = effective_views(INSTANCE, [BASE])
    assert [view.label for view in views] == ["consensus", "a", "b"]
    assert views[0].set_id is None


def test_every_declared_set_reads_the_instance_back_unchanged():
    for view in effective_views(INSTANCE, [BASE]):
        assert view.lossless, f"{view.label}: {view.error or view.restored}"
        assert view.triples == 3


def test_a_set_that_drops_a_term_is_reported_lossy():
    """A synonym with no IRI leaves the term undefined, so its key never reaches the graph."""
    schema = {
        "@context": {"ex": "https://example.org/", "id": "@id", "name": "ex:name"},
        "x-oold-context": {"name": {"": {"x-oold-sssom": {"mapping_set_id": SET_A}}}},
    }
    views = {view.label: view for view in effective_views({"@id": "https://example.org/t", "name": "x"}, [schema])}
    assert views["consensus"].lossless
    assert not views["a"].lossless


def test_a_key_the_context_does_not_define_makes_the_reading_lossy():
    instance = {"@id": "https://example.org/thing", "name": "a name", "unmapped": "lost"}
    view = effective_views(instance, [BASE], set_ids=[None])[0]
    assert not view.lossless
    assert view.undefined == ["unmapped"]


def test_a_reading_that_only_changes_the_shape_still_counts_as_lossless():
    """A community may state the edge the other way; the graph is what has to survive."""
    schema = {
        "@context": {
            "ex": "https://example.org/",
            "other": "https://other.example/",
            "id": "@id",
            "part": {"@id": "ex:part"},
        },
        "x-oold-context": {
            "part": {"other:partOf": {"@reverse": "other:partOf", "x-oold-sssom": {"mapping_set_id": SET_A}}}
        },
    }
    instance = {"@id": "https://example.org/whole", "part": {"id": "https://example.org/piece"}}
    views = {view.label: view for view in effective_views(instance, [schema])}
    assert views["a"].lossless
    assert views["a"].triples == 1


def test_a_broken_promoted_context_is_reported_rather_than_raised():
    schema = {
        "@context": {"ex": "https://example.org/", "name": "ex:name"},
        "x-oold-context": {"name": {"other:label": {"@type": "not-an-iri", "x-oold-sssom": {"mapping_set_id": SET_A}}}},
    }
    view = effective_views({"name": "x"}, [schema], set_ids=[SET_A])[0]
    assert not view.lossless
    assert view.error


def test_effective_context_resolves_a_scoped_reference_when_a_source_is_given():
    class Source:
        def locate(self, target, origin=None):
            return target if target == "Leaf.schema.json" else None

        def read(self, key):
            return {"@context": {"leaf": "ex:leaf"}}

        def term_chain(self, key):
            return [key]

    schema = {"@context": {"part": {"@id": "ex:part", "@context": "Leaf.schema.json"}}}
    assert effective_context([schema])["part"]["@context"] == "Leaf.schema.json"
    assert effective_context([schema], None, "Root.schema.json", Source())["part"]["@context"] == {"leaf": "ex:leaf"}


def test_canonical_drops_the_metadata_keys_but_keeps_order_and_cardinality():
    value = {"$schema": "S", "@context": {}, "a": ["y", "x"], "b": "one"}
    assert canonical(value) == {"a": ["y", "x"], "b": "one"}
    assert canonical({"a": ["x"]}) != canonical({"a": "x"})


def test_undefined_terms_looks_inside_nested_values():
    assert undefined_terms({"a": {"b": 1}}, {"a": "ex:a"}) == {"b"}
    assert undefined_terms({"@id": "x", "$schema": "y"}, {}) == set()


def test_view_checks_report_one_record_per_reading():
    checks = view_checks(
        "Thing.instance.json",
        [View(set_id=None, label="consensus", lossless=True, triples=3), View(set_id=SET_A, label="a", lossless=False)],
    )
    assert [check.status for check in checks] == ["ok", "fail"]
    assert {check.id for check in checks} == {CHECK_ID}
    assert checks[0].detail["triples"] == 3
    assert checks[1].detail["set"] == SET_A


def test_a_context_that_cannot_be_assembled_is_reported_as_a_failed_reading():
    """The context is built before anything is read, so its failure has its own path."""

    class Source:
        def locate(self, target, origin=None):
            raise AssertionError("not reached: the fragment is refused first")

        def read(self, key):
            raise AssertionError("not reached")

        def term_chain(self, key):
            raise AssertionError("not reached")

    schema = {"@context": {"part": {"@id": "ex:part", "@context": "#/$defs/Leaf"}}}
    view = effective_views({"part": {}}, [schema], "Root.schema.json", Source(), set_ids=[None])[0]

    assert not view.lossless
    assert "part" in view.error
    assert view.context == {}


def test_undefined_terms_looks_inside_a_list_of_nodes():
    assert undefined_terms({"items": [{"a": 1}, {"b": 2}]}, {"items": "ex:items", "a": "ex:a"}) == {"b"}


def test_view_checks_spell_out_each_outcome():
    checks = view_checks(
        "Thing.instance.json",
        [
            View(set_id=None, label="consensus", lossless=True, triples=3),
            View(set_id=SET_A, label="a", lossless=False, error="boom"),
            View(set_id=SET_B, label="b", lossless=False, undefined=["unmapped"]),
            View(set_id=SET_A, label="c", lossless=False, triples=2),
        ],
    )
    messages = [check.message for check in checks]
    assert messages[0] == "consensus: lossless round-trip, 3 triples"
    assert messages[1] == "a: could not be read (boom)"
    assert messages[2] == "b: terms not defined in the context: unmapped"
    assert messages[3] == "c: lossy round-trip, 2 triples"
    assert checks[1].detail["error"] == "boom"
    assert checks[2].detail["undefined_terms"] == ["unmapped"]
