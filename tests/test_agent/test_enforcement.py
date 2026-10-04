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
    def test_every_arm_exists(self):
        assert sorted(ARMS) == [
            "catalog-flat-enforced",
            "no-catalog-not-enforced",
            "no-catalog-not-enforced-prose",
            "schema-dump-catalog-enforced",
            "schema-dump-catalog-enforced-strict",
            "schema-dump-catalog-flat-enforced",
            "schema-dump-catalog-flat-enforced-grounded",
            "schema-dump-catalog-flat-enforced-strict",
            "schema-dump-catalog-not-enforced-gated",
        ]

    def test_an_arm_name_is_readable_without_a_legend(self):
        """Every name composes from what varies, so a table needs no key.

        The first half names what the prompt carries and the second what the
        decoder accepts. An arm whose name parses into neither is a rung
        nobody can place in a result table.
        """
        carries = ("no-catalog-", "catalog-", "schema-dump-catalog-")
        accepts = ("not-enforced", "flat-enforced", "enforced")
        for name in ARMS:
            head = max((c for c in carries if name.startswith(c)), key=len)
            rest = name[len(head) :]
            assert any(rest.startswith(a) for a in accepts), name

    def test_a_strict_arm_differs_from_its_base_only_in_the_grammar(self):
        """Or the third rung would not be a rung on the same ladder.

        A rung and its ``-strict`` form send the same schema. The difference
        is whether the provider enforces it or is merely shown it, which 589
        cells answering outside a pinned enum show is not the same thing.
        """
        for base, strict in (
            ("schema-dump-catalog-flat-enforced", "schema-dump-catalog-flat-enforced-strict"),
            ("schema-dump-catalog-enforced", "schema-dump-catalog-enforced-strict"),
        ):
            loose, tight = ARMS[base], ARMS[strict]
            assert tight.decode_strict is True
            assert loose.decode_strict is False
            assert loose.schema_in_prompt == tight.schema_in_prompt
            assert loose.decode_constraint == tight.decode_constraint
            assert loose.commit_gate == tight.commit_gate
            assert loose.validate_output == tight.validate_output

    def test_the_union_arm_differs_from_the_enum_arm_only_in_the_constraint(self):
        """Or a measured difference has two candidate causes."""
        enum_arm, union_arm = ARMS["schema-dump-catalog-flat-enforced"], ARMS["schema-dump-catalog-enforced"]
        assert enum_arm.schema_in_prompt == union_arm.schema_in_prompt
        assert enum_arm.commit_gate == union_arm.commit_gate
        assert enum_arm.grounding == union_arm.grounding
        assert enum_arm.decode_constraint is not union_arm.decode_constraint

    def test_the_enforced_only_arm_differs_from_a2_only_in_what_is_shown(self):
        shown, enforced = ARMS["schema-dump-catalog-flat-enforced"], ARMS["catalog-flat-enforced"]
        assert shown.decode_constraint is enforced.decode_constraint
        assert shown.schema_in_prompt is True
        assert enforced.schema_in_prompt is False

    def test_a0_offers_no_schema_and_no_catalogue(self):
        for name in ("no-catalog-not-enforced-prose", "no-catalog-not-enforced"):
            condition = ARMS[name]
            assert condition.schema_in_prompt is False
            assert condition.catalogue is None
            assert condition.commit_gate is False

    def test_the_two_a0_arms_differ_only_in_output_form(self):
        prose, as_json = ARMS["no-catalog-not-enforced-prose"], ARMS["no-catalog-not-enforced"]
        assert prose.output_form is OutputForm.PROSE
        assert as_json.output_form is OutputForm.JSON
        for field in ("schema_in_prompt", "catalogue", "commit_gate", "grounding"):
            assert getattr(prose, field) == getattr(as_json, field)

    def test_a1_to_a2_varies_only_the_decode_constraint(self):
        """The cheapest real contrast in the study, so nothing else may move."""
        a1, a2 = ARMS["schema-dump-catalog-not-enforced-gated"], ARMS["schema-dump-catalog-flat-enforced"]
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
        a2, a3 = ARMS["schema-dump-catalog-flat-enforced"], ARMS["schema-dump-catalog-flat-enforced-grounded"]
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
        condition = arm("schema-dump-catalog-flat-enforced", ("a.B", "a.C"))
        assert condition.catalogue == ("a.B", "a.C")
        assert condition.catalogue_size == 2

    def test_arm_refuses_a_catalogue_on_an_arm_that_offers_none(self):
        with pytest.raises(ValueError, match="offers no catalogue"):
            arm("no-catalog-not-enforced", ("a.B",))

    def test_unknown_arm_is_refused(self):
        with pytest.raises(KeyError, match="unknown arm"):
            arm("A9-nonesuch")


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


def test_orchestration_covers_single_shot_and_the_three_reference_agents():
    assert [o.value for o in Orchestration] == [
        "single_shot",
        "recursive",
        "segmented",
        "multi_step",
        "select_then_fill",
    ]


class TestClosingTheUnitSlot:
    """A quantity corpus enumerates the units each kind admits."""

    def test_an_arm_carries_no_unit_enumeration_by_default(self):
        assert arm("schema-dump-catalog-flat-enforced", ("Length",)).unit_catalogue is None

    def test_units_can_be_set_without_touching_the_catalogue(self):
        enforcement = arm("schema-dump-catalog-flat-enforced", ("Length",)).with_units(("meter", "foot"))
        assert enforcement.unit_catalogue == ("meter", "foot")
        assert enforcement.catalogue == ("Length",)

    def test_the_unit_enumeration_is_reported(self):
        """A closed slot nobody records looks like a free one."""
        described = arm("schema-dump-catalog-flat-enforced", ("Length",)).with_units(("meter", "foot")).describe()
        assert described["unit_catalogue_size"] == 2

    def test_no_unit_enumeration_reports_zero(self):
        assert arm("schema-dump-catalog-flat-enforced", ("Length",)).describe()["unit_catalogue_size"] == 0
