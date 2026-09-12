"""Reading synonyms out of a schema chain.

The behaviour these pin down is the one the generators in oold-reference-schemas rely on, so
a change here shows up as a different published mapping set rather than as a subtle difference
in what an instance is taken to mean.
"""

import pytest

from oold.utils.mappings import (
    chain,
    context_of,
    declared_context,
    is_exact_match,
    mapping_sets,
    promote,
    set_name,
    synonym_entries,
    synonyms_of,
)

SET_A = "https://example.org/sets/a"
SET_B = "https://example.org/sets/b"


def _schema(context, synonyms=None, **extra):
    schema = {"@context": context}
    if synonyms is not None:
        schema["x-oold-context"] = synonyms
    schema.update(extra)
    return schema


def test_context_of_merges_a_list_in_order():
    """A later entry wins, which is what makes a subschema able to override a base term."""
    schema = _schema(["ignored-remote-reference", {"a": "ex:a"}, {"a": "ex:override", "b": "ex:b"}])
    assert context_of(schema) == {"a": "ex:override", "b": "ex:b"}


def test_context_of_tolerates_a_missing_or_scalar_context():
    assert context_of({}) == {}
    assert context_of({"@context": "Remote.schema.json"}) == {}


def test_declared_context_is_base_first():
    base = _schema({"name": "ex:base_name", "shared": "ex:base"})
    derived = _schema({"name": "ex:derived_name"})
    assert declared_context([base, derived]) == {"name": "ex:derived_name", "shared": "ex:base"}


def test_mapping_sets_are_collected_over_the_whole_chain():
    """A subschema inherits its base's mappings, so a reading exists for a set it never names."""
    base = _schema(
        {"name": "ex:name"},
        {"name": {"other:name": {"x-oold-sssom": {"mapping_set_id": SET_A}}}},
    )
    derived = _schema(
        {"age": "ex:age"},
        {"age": {"other:age": {"x-oold-sssom": {"mapping_set_id": SET_B}}}},
    )
    assert mapping_sets([base, derived]) == sorted([SET_A, SET_B])


def test_an_entry_may_belong_to_several_sets():
    """The specification allows a list; the upstream generator only ever saw a string."""
    schema = _schema(
        {"name": "ex:name"},
        {"name": {"other:name": {"x-oold-sssom": {"mapping_set_id": [SET_A, SET_B]}}}},
    )
    assert mapping_sets([schema]) == sorted([SET_A, SET_B])
    assert promote(declared_context([schema]), [schema], SET_A)["name"] == "other:name"
    assert promote(declared_context([schema]), [schema], SET_B)["name"] == "other:name"


def test_promote_without_a_set_is_the_consensus_context():
    schema = _schema(
        {"name": "ex:name"},
        {"name": {"other:name": {"x-oold-sssom": {"mapping_set_id": SET_A}}}},
    )
    assert promote(declared_context([schema]), [schema], None) == {"name": "ex:name"}


def test_promote_keeps_the_primary_type_coercion():
    """Only the IRI moves; a promoted term still coerces its values the same way."""
    schema = _schema(
        {"works_for": {"@id": "ex:worksFor", "@type": "@id"}},
        {"works_for": {"other:memberOf": {"x-oold-sssom": {"mapping_set_id": SET_A}}}},
    )
    promoted = promote(declared_context([schema]), [schema], SET_A)
    assert promoted["works_for"] == {"@id": "other:memberOf", "@type": "@id"}


def test_promote_uses_reverse_rather_than_id_for_an_inverted_synonym():
    """A term definition carrying both @id and @reverse is not valid JSON-LD."""
    schema = _schema(
        {"employs": {"@id": "ex:employs", "@type": "@id"}},
        {
            "employs": {
                "other:worksFor": {
                    "@reverse": "other:worksFor",
                    "@type": "@id",
                    "x-oold-sssom": {"mapping_set_id": SET_A},
                }
            }
        },
    )
    promoted = promote(declared_context([schema]), [schema], SET_A)
    assert promoted["employs"]["@reverse"] == "other:worksFor"
    assert "@id" not in promoted["employs"]


def test_a_null_entry_is_not_a_synonym():
    """`null` removes an inherited mapping under composition; it does not add one."""
    schema = _schema({"name": "ex:name"}, {"name": {"other:name": None}})
    assert synonyms_of(schema) == {}
    assert mapping_sets([schema]) == []


def test_exact_match_is_the_default_and_others_are_excluded():
    assert is_exact_match({}) is True
    assert is_exact_match({"x-oold-sssom": {"predicate_id": "skos:exactMatch"}}) is True
    assert is_exact_match({"x-oold-sssom": {"predicate_id": "http://www.w3.org/2004/02/skos/core#exactMatch"}}) is True
    assert is_exact_match({"x-oold-sssom": {"predicate_id": "skos:closeMatch"}}) is False

    schema = _schema(
        {"name": "ex:name", "nick": "ex:nick"},
        {
            "name": {"other:name": {}},
            "nick": {"other:nick": {"x-oold-sssom": {"predicate_id": "skos:broadMatch"}}},
        },
    )
    assert [iri for iri, _, _ in synonym_entries([schema])] == ["other:name"]


@pytest.mark.parametrize(
    ("iri", "expected"),
    [
        ("https://example.org/sets/emmo", "emmo"),
        ("https://example.org/sets/emmo/", "emmo"),
        ("https://example.org/sets/emmo.sssom.tsv", "emmo"),
    ],
)
def test_set_name(iri, expected):
    assert set_name(iri) == expected


def test_chain_follows_allof_refs_base_first():
    base = {"title": "Base", "@context": {"a": "ex:a"}}
    middle = {"title": "Middle", "allOf": [{"$ref": "Base.schema.json"}]}
    derived = {"title": "Derived", "allOf": [{"$ref": "Middle.schema.json"}]}
    documents = {"Base.schema.json": base, "Middle.schema.json": middle}

    result = chain(derived, documents.get)

    assert [s["title"] for s in result] == ["Base", "Middle", "Derived"]


def test_chain_skips_a_reference_it_cannot_resolve():
    """A playground holds half-written input; an unreachable base must not fail the render."""
    derived = {"title": "Derived", "allOf": [{"$ref": "https://example.invalid/Nope.json"}]}
    assert [s["title"] for s in chain(derived, lambda _ref: None)] == ["Derived"]


def test_chain_reads_an_inline_allof_branch():
    derived = {"title": "Derived", "allOf": [{"@context": {"b": "ex:b"}}]}
    assert declared_context(chain(derived, None)) == {"b": "ex:b"}
