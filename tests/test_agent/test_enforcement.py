"""The enforcement axis: arms are values, and the invalid ones are refused."""

import pytest

from oold.agent import (
    ARMS,
    DecodeConstraint,
    Enforcement,
    Orchestration,
    OutputForm,
    arm,
)


def typed(**overrides) -> Enforcement:
    kwargs = {
        "schema_in_prompt": True,
        "catalogue": ("schemaorg.Person",),
        "decode_constraint": DecodeConstraint.JSON_SCHEMA_ENUM,
        "commit_gate": True,
        "grounding": False,
    }
    kwargs.update(overrides)
    return Enforcement(**kwargs)


class TestArms:
    def test_all_five_arms_exist(self):
        assert sorted(ARMS) == ["A0-json", "A0-prose", "A1", "A2", "A3"]

    def test_a0_offers_no_schema_and_no_catalogue(self):
        for name in ("A0-prose", "A0-json"):
            condition = ARMS[name]
            assert condition.schema_in_prompt is False
            assert condition.catalogue is None
            assert condition.commit_gate is False

    def test_the_two_a0_arms_differ_only_in_output_form(self):
        prose, as_json = ARMS["A0-prose"], ARMS["A0-json"]
        assert prose.output_form is OutputForm.PROSE
        assert as_json.output_form is OutputForm.JSON
        for field in ("schema_in_prompt", "catalogue", "commit_gate", "grounding"):
            assert getattr(prose, field) == getattr(as_json, field)

    def test_a1_to_a2_varies_only_the_decode_constraint(self):
        """The cheapest real contrast in the study, so nothing else may move."""
        a1, a2 = ARMS["A1"], ARMS["A2"]
        assert a1.decode_constraint is DecodeConstraint.NONE
        assert a2.decode_constraint is DecodeConstraint.JSON_SCHEMA_ENUM
        for field in (
            "schema_in_prompt",
            "catalogue",
            "commit_gate",
            "grounding",
            "output_form",
        ):
            assert getattr(a1, field) == getattr(a2, field)

    def test_a2_to_a3_varies_only_grounding(self):
        a2, a3 = ARMS["A2"], ARMS["A3"]
        assert a2.grounding is False
        assert a3.grounding is True
        for field in (
            "schema_in_prompt",
            "catalogue",
            "commit_gate",
            "decode_constraint",
            "output_form",
        ):
            assert getattr(a2, field) == getattr(a3, field)

    def test_arm_applies_a_catalogue(self):
        condition = arm("A2", ("a.B", "a.C"))
        assert condition.catalogue == ("a.B", "a.C")
        assert condition.catalogue_size == 2

    def test_arm_refuses_a_catalogue_on_an_arm_that_offers_none(self):
        with pytest.raises(ValueError, match="offers no catalogue"):
            arm("A0-json", ("a.B",))

    def test_unknown_arm_is_refused(self):
        with pytest.raises(KeyError, match="unknown arm"):
            arm("A4")


class TestEnforcement:
    def test_no_catalogue_is_not_an_empty_catalogue(self):
        """Offering nothing and offering an empty list are different arms."""
        assert typed(catalogue=None).catalogue_size == 0
        assert typed(catalogue=()).catalogue_size == 0
        assert typed(catalogue=None).describe()["catalogue_offered"] is False
        assert typed(catalogue=()).describe()["catalogue_offered"] is True

    def test_grounding_without_a_schema_is_refused(self):
        with pytest.raises(ValueError, match="needs a schema to ground"):
            typed(schema_in_prompt=False, grounding=True)

    def test_prose_cannot_carry_a_decode_constraint(self):
        with pytest.raises(ValueError, match="cannot carry a decode-time"):
            typed(
                output_form=OutputForm.PROSE,
                decode_constraint=DecodeConstraint.JSON_SCHEMA,
                commit_gate=False,
            )

    def test_prose_cannot_carry_a_commit_gate(self):
        with pytest.raises(ValueError, match="no class path to gate"):
            typed(
                output_form=OutputForm.PROSE,
                decode_constraint=DecodeConstraint.NONE,
                commit_gate=True,
            )

    def test_with_catalogue_changes_nothing_else(self):
        before = typed()
        after = before.with_catalogue(("x.Y",) * 50)
        assert after.catalogue_size == 50
        for field in (
            "schema_in_prompt",
            "decode_constraint",
            "commit_gate",
            "grounding",
        ):
            assert getattr(before, field) == getattr(after, field)

    def test_describe_omits_catalogue_contents(self):
        described = typed(catalogue=("a.B",) * 900).describe()
        assert described["catalogue_size"] == 900
        assert "catalogue" not in described

    def test_is_frozen(self):
        with pytest.raises(Exception):
            setattr(typed(), "commit_gate", False)  # noqa: B010


def test_orchestration_covers_the_three_reference_agents():
    assert [o.value for o in Orchestration] == [
        "recursive",
        "segmented",
        "multi_step",
    ]
