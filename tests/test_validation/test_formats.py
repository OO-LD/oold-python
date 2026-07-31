"""Format assertion, including the deliberate iri/iri-reference override."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oold.validation.formats import (
    FORMAT_SAMPLES,
    OOLD_FORMAT_CHECKER,
    is_iri,
    is_iri_reference,
)

PARITY = json.loads((Path(__file__).parent.parent / "data" / "format_parity.json").read_text(encoding="utf-8"))[
    "formats"
]

PARITY_CASES = [
    (name, value, expected) for name, values in sorted(PARITY.items()) for value, expected in values.items()
]


@pytest.mark.parametrize("name,value,expected", PARITY_CASES, ids=lambda v: str(v)[:30])
def test_matches_the_reference_toolchain(name, value, expected):
    """Every outcome here was captured from ajv, as the reference harness configures it.

    `format` is an assertion in this pipeline, so a disagreement with ajv is a disagreement
    about whether a schema is satisfiable, which is exactly the kind of divergence the port
    exists to avoid. Two cases are load-bearing and easy to get wrong: ajv-formats runs in
    *full* mode, so `time` requires an offset and `email` requires a dotted domain.
    """
    assert OOLD_FORMAT_CHECKER.conforms(value, name) is expected


@pytest.mark.parametrize("name,sample", sorted(FORMAT_SAMPLES.items()))
def test_every_generator_sample_satisfies_its_own_checker(name, sample):
    """The generator emits these, and the validator then asserts them. They must agree."""
    assert OOLD_FORMAT_CHECKER.conforms(sample, name), f"{name} sample {sample!r} is invalid"


@pytest.mark.parametrize(
    "name,value",
    [
        ("date", "2026-13-01"),
        ("date", "2026-02-30"),
        ("date", "not-a-date"),
        ("date-time", "2026-01-02T03:04:05"),  # no offset
        ("time", "25:00:00"),
        ("time", "03:04:05"),  # full mode requires an offset
        ("duration", "1D"),
        ("duration", "P"),
        ("email", "not-an-email"),
        ("uuid", "not-a-uuid"),
        ("ipv4", "999.0.0.1"),
        ("ipv6", "not::a::v6"),
        ("regex", "([unclosed"),
        ("uri", "https://exa mple.org"),
        ("uri", "relative/path"),
        ("iri", "not an iri"),
        ("iri", "relative/path"),
        ("iri-reference", 'has"quote'),
    ],
)
def test_invalid_values_are_rejected(name, value):
    assert not OOLD_FORMAT_CHECKER.conforms(value, name)


@pytest.mark.parametrize(
    "value",
    ["ex:alice", "urn:uuid:6e8bc430-9c3a-11d9-9669-0800200c9a66", "https://example.org/x"],
)
def test_compact_and_urn_iris_are_accepted(value):
    """The override exists because ajv-formats-draft2019 wrongly rejects these.

    A compact IRI is a valid IRI: an IRI is a superset of a URI. The reference harness patches
    the same two formats, so rejecting these would make the two implementations disagree on
    most OO-LD schemas.
    """
    assert is_iri(value)
    assert is_iri_reference(value)
    assert OOLD_FORMAT_CHECKER.conforms(value, "iri")


def test_iri_reference_accepts_relative_but_iri_does_not():
    assert is_iri_reference("Thing.schema.json")
    assert not is_iri("Thing.schema.json")


def test_non_strings_are_not_constrained():
    """`format` applies to strings only; a number under `format: iri` is not a format error."""
    for name in FORMAT_SAMPLES:
        assert OOLD_FORMAT_CHECKER.conforms(42, name)
        assert OOLD_FORMAT_CHECKER.conforms(None, name)


def test_iri_allows_non_ascii_but_uri_does_not():
    assert is_iri_reference("https://example.org/ünïcode")
    assert not OOLD_FORMAT_CHECKER.conforms("https://example.org/ünïcode", "uri")
