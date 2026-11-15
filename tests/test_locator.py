"""Resolving a published IRI to a file in a working tree.

The point of these is that a build stays offline: a schema that names another by its published
IRI must be read from the tree being edited, not fetched, and a layout this library does not
know must be expressible as a rule rather than as a patch.
"""

import json

import pytest

from oold.utils.locator import Locator, MirrorRule

BASE = "https://example.org/schemas/"
RULE = MirrorRule(BASE, "{0}/{2}", 3)


def write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return str(path.resolve())


@pytest.fixture
def tree(tmp_path):
    """Two modules, one referring to the other by its published IRI."""
    root = tmp_path / "modules"
    write(root / "quantities" / "Length.schema.json", {"@context": {"value": "ex:value"}})
    write(
        root / "materials" / "Material.schema.json",
        {
            "@context": {"length": {"@id": "ex:length", "@context": f"{BASE}quantities/0.2/Length.schema.json"}},
            "allOf": [{"$ref": "Base.schema.json"}],
        },
    )
    write(root / "materials" / "Base.schema.json", {"@context": {"name": "ex:name"}})
    return root


def test_a_published_iri_resolves_to_the_file_in_the_tree(tree):
    locator = Locator(tree, [RULE])
    key = locator.locate(f"{BASE}quantities/0.2/Length.schema.json")
    assert key == str((tree / "quantities" / "Length.schema.json").resolve())


def test_the_version_segment_is_ignored_because_the_tree_holds_one_version(tree):
    locator = Locator(tree, [RULE])
    first = locator.locate(f"{BASE}quantities/0.2/Length.schema.json")
    second = locator.locate(f"{BASE}quantities/9.9/Length.schema.json")
    assert first == second


def test_a_rule_that_does_not_match_the_segment_count_is_not_applied(tree):
    """Without the count a shorter IRI would format against the wrong segments."""
    locator = Locator(tree, [RULE])
    assert locator.locate(f"{BASE}quantities/Length.schema.json") is None


def test_an_unknown_iri_is_not_resolved(tree):
    locator = Locator(tree, [RULE])
    assert locator.locate("https://other.example/Thing.schema.json") is None


def test_a_relative_reference_resolves_against_the_referring_document(tree):
    locator = Locator(tree, [RULE])
    origin = str((tree / "materials" / "Material.schema.json").resolve())
    assert locator.locate("Base.schema.json", origin) == str((tree / "materials" / "Base.schema.json").resolve())


def test_a_relative_reference_without_an_origin_resolves_to_nothing(tree):
    assert Locator(tree, [RULE]).locate("Base.schema.json") is None


def test_a_fragment_selects_part_of_a_document_and_not_another_document(tree):
    locator = Locator(tree, [RULE])
    origin = str((tree / "materials" / "Material.schema.json").resolve())
    assert locator.locate("Base.schema.json#/$defs/X", origin) == locator.locate("Base.schema.json", origin)
    assert locator.locate("#/$defs/X", origin) == origin


def test_term_chain_follows_allof_context_and_ref_with_the_document_last(tree):
    locator = Locator(tree, [RULE])
    key = str((tree / "materials" / "Material.schema.json").resolve())
    walked = locator.term_chain(key)
    assert walked[-1] == key
    assert str((tree / "materials" / "Base.schema.json").resolve()) in walked
    assert str((tree / "quantities" / "Length.schema.json").resolve()) not in walked


def test_term_chain_reaches_a_schema_named_only_by_a_property_ref(tmp_path):
    """A property's target defines the terms of the embedded object; miss it and its keys are dropped."""
    root = tmp_path / "modules"
    write(root / "m" / "Leaf.schema.json", {"@context": {"leaf": "ex:leaf"}})
    key = write(root / "m" / "Root.schema.json", {"properties": {"part": {"$ref": "Leaf.schema.json"}}})
    walked = Locator(root).term_chain(key)
    assert walked == [str((root / "m" / "Leaf.schema.json").resolve()), key]


def test_term_chain_terminates_on_a_reference_cycle(tmp_path):
    root = tmp_path / "modules"
    a = write(root / "m" / "A.schema.json", {"properties": {"b": {"$ref": "B.schema.json"}}})
    b = write(root / "m" / "B.schema.json", {"properties": {"a": {"$ref": "A.schema.json"}}})
    assert set(Locator(root).term_chain(a)) == {a, b}


def test_term_chain_skips_a_reference_the_tree_cannot_reach(tmp_path):
    root = tmp_path / "modules"
    key = write(root / "m" / "Root.schema.json", {"allOf": [{"$ref": "https://elsewhere.example/Gone.schema.json"}]})
    assert Locator(root).term_chain(key) == [key]


def test_loader_feeds_the_inheritance_chain(tree):
    from oold.utils.mappings import chain, declared_context

    locator = Locator(tree, [RULE])
    key = str((tree / "materials" / "Material.schema.json").resolve())
    lineage = chain(locator.read(key), locator.loader(key))
    assert declared_context(lineage)["name"] == "ex:name"


def test_a_document_is_read_once(tree):
    locator = Locator(tree, [RULE])
    key = str((tree / "materials" / "Base.schema.json").resolve())
    first = locator.read(key)
    assert locator.read(key) is first


def test_a_relative_reference_cannot_escape_the_root(tree):
    """A reference is attacker-controlled input to a library, not a path typed by the author."""
    outside = tree.parent / "secret.json"
    write(outside, {"@context": {"secret": "ex:secret"}})
    locator = Locator(tree, [RULE])
    origin = str((tree / "materials" / "Material.schema.json").resolve())
    assert locator.locate("../../secret.json", origin) is None


def test_a_dot_segment_inside_an_iri_cannot_escape_the_root(tree):
    outside = tree.parent / "secret.json"
    write(outside, {"@context": {}})
    locator = Locator(tree, [RULE])
    assert locator.locate(f"{BASE}../0.1/secret.json") is None


def test_without_a_root_a_reference_cannot_leave_the_referring_directory(tmp_path):
    root = tmp_path / "modules"
    origin = write(root / "m" / "Root.schema.json", {})
    write(tmp_path / "secret.json", {})
    assert Locator().locate("../../secret.json", origin) is None
    assert Locator().locate("Root.schema.json", origin) == origin


def test_a_malformed_document_in_the_chain_is_raised_not_skipped(tmp_path):
    """A dropped document shortens the chain, so fewer terms are inlined and the run stays green."""
    root = tmp_path / "modules"
    broken = root / "m" / "Leaf.schema.json"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("{ not json", encoding="utf-8")
    key = write(root / "m" / "Root.schema.json", {"properties": {"part": {"$ref": "Leaf.schema.json"}}})
    with pytest.raises(json.JSONDecodeError):
        Locator(root).term_chain(key)


def test_a_target_that_is_not_a_reference_resolves_to_nothing(tree):
    locator = Locator(tree, [RULE])
    assert locator.locate("") is None
    assert locator.locate(None) is None
    assert locator.locate(123) is None


def test_a_template_that_names_a_segment_the_iri_does_not_have_is_not_applied(tree):
    """Without this the rule would raise instead of declining, on input it simply does not cover."""
    rule = MirrorRule(BASE, "{0}/{7}", None)
    assert Locator(tree, [rule]).locate(f"{BASE}quantities/0.2/Length.schema.json") is None


def test_term_chain_follows_a_schema_named_as_a_string_context(tmp_path):
    """A schema may name another as its whole `@context`, which is how a base lends its terms."""
    root = tmp_path / "modules"
    base = write(root / "m" / "Base.schema.json", {"@context": {"name": "ex:name"}})
    key = write(root / "m" / "Derived.schema.json", {"@context": ["Base.schema.json", {"size": "ex:size"}]})
    assert Locator(root).term_chain(key) == [base, key]


def test_a_rule_whose_path_escapes_the_root_falls_through_to_the_relative_branch(tree):
    """The rule declines, and resolution continues rather than stopping at the escape."""
    escaping = MirrorRule(BASE, "../{0}", 1)
    locator = Locator(tree, [escaping, RULE])
    assert locator.locate(f"{BASE}quantities/0.2/Length.schema.json") == str(
        (tree / "quantities" / "Length.schema.json").resolve()
    )
