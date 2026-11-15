"""Deriving SSSOM mapping sets from the mappings a schema carries inline.

A set is derived, never maintained, so what these pin down is that deriving it twice gives the
same file, and that a chained mapping is never passed off as a curated one.
"""

from oold.utils.sssom import (
    CHAINED,
    COLUMNS,
    CONSENSUS,
    CURATED,
    EXACT,
    SchemaGroup,
    collect,
    compose,
    crosswalk,
    expand,
    prefixes,
    render_set,
    strip_version,
    target,
)

OWN = "https://example.org/schemas/"
SET_A = "https://example.org/sets/emmo.sssom.tsv"

SCHEMA = {
    "@context": {
        "ex": "https://vocab.example/",
        "own": {"@id": f"{OWN}materials/0.2/Thing.schema.json#", "@prefix": True},
        "Thing": f"{OWN}materials/0.2/Thing.schema.json",
        "name": "ex:name",
    },
    "x-oold-context": {
        "name": {
            "ex:label": {"x-oold-sssom": {"mapping_set_id": SET_A, "comment": "close enough", "predicate_id": EXACT}}
        }
    },
}


def group(*schemas):
    return SchemaGroup("https://example.org/schemas/materials", "0.2.0", list(schemas))


def test_prefixes_reads_a_declared_prefix_and_a_delimited_string():
    context = {
        "a": {"@id": "https://a.example/x", "@prefix": True},
        "b": "https://b.example/",
        "c": "https://c.example/term",
    }
    assert prefixes(context) == {"a": "https://a.example/x", "b": "https://b.example/"}


def test_expand_leaves_an_absolute_iri_and_an_unknown_prefix_alone():
    curies = {"ex": "https://vocab.example/"}
    assert expand("ex:name", curies) == "https://vocab.example/name"
    assert expand("https://x.example/y", curies) == "https://x.example/y"
    assert expand("other:name", curies) == "other:name"


def test_target_ignores_a_keyword_alias():
    assert target({"@id": "ex:name"}) == "ex:name"
    assert target("ex:name") == "ex:name"
    assert target("@type") is None


def test_strip_version_drops_the_version_segment_only():
    assert strip_version(f"{OWN}materials/0.2/Thing.schema.json", OWN) == f"{OWN}materials/Thing.schema.json"
    assert strip_version("https://other.example/a/b/c", OWN) == "https://other.example/a/b/c"
    assert strip_version(f"{OWN}materials/0.2", OWN) == f"{OWN}materials/0.2"


def test_the_consensus_mappings_become_a_set_of_their_own():
    sets, _ = collect([group(SCHEMA)], own_prefix=OWN)
    assert CONSENSUS in sets
    rows = {row["subject_label"]: row for row in sets[CONSENSUS]}
    assert rows["name"]["object_id"] == "ex:name"
    assert rows["name"]["mapping_justification"] == CURATED


def test_a_term_mapped_to_a_placeholder_of_the_library_is_identified_by_it():
    """A term name alone does not identify a term, so the placeholder is the subject."""
    sets, _ = collect([group(SCHEMA)], own_prefix=OWN)
    rows = {row["subject_label"]: row for row in sets[CONSENSUS]}
    assert rows["Thing"]["subject_id"] == f"{OWN}materials/Thing.schema.json"
    assert rows["name"]["subject_id"] == "https://example.org/schemas/materials#name"


def test_a_placeholder_is_not_stated_to_match_itself():
    schema = {"@context": {"Thing": f"{OWN}Thing.schema.json"}}
    sets, _ = collect([group(schema)], own_prefix=OWN)
    assert CONSENSUS not in sets


def test_a_versioned_placeholder_still_maps_its_unversioned_identity_to_the_release():
    """The subject keeps its identity across releases; the version it was written for is data."""
    schema = {"@context": {"Thing": f"{OWN}materials/0.2/Thing.schema.json"}}
    sets, _ = collect([group(schema)], own_prefix=OWN)
    row = sets[CONSENSUS][0]
    assert row["subject_id"] == f"{OWN}materials/Thing.schema.json"
    assert row["object_id"] == f"{OWN}materials/0.2/Thing.schema.json"
    assert row["subject_source_version"] == "0.2.0"


def test_a_synonym_lands_in_the_set_it_names_with_its_metadata():
    sets, _ = collect([group(SCHEMA)], own_prefix=OWN)
    assert list(sets) == [CONSENSUS, "emmo"]
    row = sets["emmo"][0]
    assert row["object_id"] == "ex:label"
    assert row["comment"] == "close enough"


def test_a_synonym_with_no_set_is_not_collected():
    schema = {"@context": {"name": "ex:name"}, "x-oold-context": {"name": {"ex:label": {}}}}
    sets, _ = collect([group(schema)], own_prefix=OWN)
    assert "emmo" not in sets


def test_a_label_is_attached_where_one_is_known():
    labels = {"https://vocab.example/label": {"label": "preferred label"}}
    sets, _ = collect([group(SCHEMA)], own_prefix=OWN, labels=labels)
    assert sets["emmo"][0]["object_label"] == "preferred label"


def test_compose_requires_an_exact_link_on_one_side():
    assert compose(EXACT, "skos:broadMatch") == "skos:broadMatch"
    assert compose("skos:broadMatch", EXACT) == "skos:broadMatch"
    assert compose("skos:closeMatch", "skos:closeMatch") is None


def test_crosswalk_chains_two_sets_through_the_term_they_share():
    left = [
        {
            "subject_id": "s",
            "subject_label": "name",
            "predicate_id": EXACT,
            "object_id": "a:name",
            "object_label": "A",
            "object_source_version": "1",
        }
    ]
    right = [
        {
            "subject_id": "s",
            "subject_label": "name",
            "predicate_id": EXACT,
            "object_id": "b:name",
            "object_label": "B",
            "object_source_version": "2",
        }
    ]
    rows = crosswalk("a", left, "b", right, {}, source_of=lambda name: f"sets/{name}")
    assert len(rows) == 1
    assert rows[0]["mapping_justification"] == CHAINED
    assert rows[0]["subject_id"] == "a:name"
    assert rows[0]["object_id"] == "b:name"
    assert rows[0]["subject_source"] == "sets/a"
    assert "chained through name" in rows[0]["comment"]


def test_crosswalk_does_not_chain_two_inexact_mappings():
    left = [
        {
            "subject_id": "s",
            "subject_label": "n",
            "predicate_id": "skos:closeMatch",
            "object_id": "a:n",
            "object_label": "",
            "object_source_version": "",
        }
    ]
    right = [
        {
            "subject_id": "s",
            "subject_label": "n",
            "predicate_id": "skos:closeMatch",
            "object_id": "b:n",
            "object_label": "",
            "object_source_version": "",
        }
    ]
    assert crosswalk("a", left, "b", right, {}) == []


def test_crosswalk_does_not_state_a_term_matches_itself():
    row = {
        "subject_id": "s",
        "subject_label": "n",
        "predicate_id": EXACT,
        "object_id": "a:n",
        "object_label": "",
        "object_source_version": "",
    }
    assert crosswalk("a", [row], "b", [dict(row)], {}) == []


def test_render_set_writes_the_preamble_the_header_and_sorted_rows():
    sets, curies = collect([group(SCHEMA)], own_prefix=OWN)
    text = render_set(
        CONSENSUS,
        sets[CONSENSUS],
        curies,
        set_id="https://example.org/mappings/consensus.sssom.tsv",
        version="1.2.3",
        title="consensus mappings",
        license="https://creativecommons.org/publicdomain/zero/1.0/",
        provider="https://example.org/provider",
    )
    lines = text.splitlines()
    assert lines[0] == "# mapping_set_id: https://example.org/mappings/consensus.sssom.tsv"
    assert "# mapping_set_version: 1.2.3" in lines
    assert "# license: https://creativecommons.org/publicdomain/zero/1.0/" in lines
    header = next(line for line in lines if not line.startswith("#"))
    assert header.split("\t") == list(COLUMNS)


def test_render_set_declares_only_the_prefixes_the_rows_use():
    sets, curies = collect([group(SCHEMA)], own_prefix=OWN)
    text = render_set("emmo", sets["emmo"], curies, set_id="https://example.org/mappings/emmo.sssom.tsv")
    assert "#   ex: https://vocab.example/" in text
    assert "#   own:" not in text
    assert "#   skos: " in text


def test_rendering_the_same_set_twice_gives_the_same_text():
    sets, curies = collect([group(SCHEMA)], own_prefix=OWN)
    first = render_set(CONSENSUS, sets[CONSENSUS], curies, set_id="s")
    second = render_set(CONSENSUS, list(reversed(sets[CONSENSUS])), curies, set_id="s")
    assert first == second


def test_a_tab_in_a_value_cannot_break_the_columns():
    rows = [
        {
            "subject_id": "s",
            "subject_label": "n",
            "predicate_id": EXACT,
            "object_id": "a:n",
            "object_label": "",
            "mapping_justification": CURATED,
            "subject_source": "",
            "subject_source_version": "",
            "object_source": "",
            "object_source_version": "",
            "comment": "has\ta tab",
        }
    ]
    body = render_set("s", rows, {}, set_id="s").splitlines()[-1]
    assert len(body.split("\t")) == len(COLUMNS)
