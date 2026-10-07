"""What each condition actually puts in front of a model.

Every difference between arms has to be visible here, because this is where
the arms differ. A condition that is recorded but never reaches the prompt is
the worst kind of bug: the record says the run was one thing and the model saw
another.
"""

from oold.agent.enforcement import arm
from oold.agent.prompts import ExtractionRequest, build_messages


def request(schema: dict | None = None) -> ExtractionRequest:
    return ExtractionRequest(
        document="The reading was 1.0 meter.",
        schema=schema if schema is not None else {"type": "object"},
    )


def sections(enforcement) -> list[str]:
    return build_messages(request(), enforcement)[0].content.split("\n\n")


def catalogue_section(enforcement) -> str:
    return next(s for s in sections(enforcement) if s.startswith("Choose the class"))


class TestTheShapeOfTheMessages:
    def test_the_document_is_the_user_message_and_nothing_else(self):
        """So a model that treats the last turn as the instruction cannot
        confuse the two."""
        messages = build_messages(request(), arm("schema-dump-catalog-flat-enforced", ("Length",)))
        assert messages[1].role == "user"
        assert messages[1].content == "The reading was 1.0 meter."

    def test_the_task_sentence_is_identical_across_arms(self):
        """A difference in wording would be a difference nobody declared."""
        first = sections(arm("schema-dump-catalog-not-enforced-gated", ("Length",)))[0]
        second = sections(arm("schema-dump-catalog-flat-enforced", ("Length",)))[0]
        assert first == second

    def test_an_arm_with_no_catalogue_gets_no_catalogue_section(self):
        assert not any(s.startswith("Choose the class") for s in sections(arm("no-catalog-not-enforced")))


class TestWhatTheCatalogueLooksLike:
    """The rendered entries have to reach the prompt, not just the record.

    This class exists because they did not. ``catalogue_text`` was plumbed
    through the condition, reported in ``describe()``, and then dropped here,
    and every test passed because none of them read the prompt.
    """

    def test_identifiers_are_listed_when_no_text_is_supplied(self):
        section = catalogue_section(arm("schema-dump-catalog-flat-enforced", ("Length", "Mass")))
        assert "- Length" in section
        assert "- Mass" in section

    def test_rendered_entries_replace_the_bare_list(self):
        enforcement = arm("schema-dump-catalog-flat-enforced", ("Length", "Mass")).with_catalogue_text((
            "- Length (Length)\n  units: meter",
            "- Mass (Mass)\n  units: gram",
        ))
        section = catalogue_section(enforcement)
        assert "units: meter" in section
        assert "units: gram" in section

    def test_the_identifier_survives_in_a_rendered_entry(self):
        """It is still the answer, however much else is shown."""
        enforcement = arm("schema-dump-catalog-flat-enforced", ("Length",)).with_catalogue_text((
            "- Length (Length)\n  units: meter",
        ))
        assert "- Length" in catalogue_section(enforcement)

    def test_every_offered_class_reaches_the_prompt(self):
        names = tuple(f"C{i}" for i in range(40))
        enforcement = arm("schema-dump-catalog-flat-enforced", names).with_catalogue_text(
            tuple(f"- {n} (label {n})" for n in names)
        )
        section = catalogue_section(enforcement)
        assert all(f"- {n} (label {n})" in section for n in names)

    def test_a_described_catalogue_is_longer_than_a_bare_one(self):
        bare = catalogue_section(arm("schema-dump-catalog-flat-enforced", ("Length",)))
        described = catalogue_section(
            arm("schema-dump-catalog-flat-enforced", ("Length",)).with_catalogue_text((
                "- Length (Length)\n  units: meter",
            ))
        )
        assert len(described) > len(bare)


class TestWhatTheSchemaSectionCarries:
    def test_an_arm_that_shows_no_schema_has_no_schema_section(self):
        assert not any(s.startswith("Each entity must conform") for s in sections(arm("no-catalog-not-enforced")))

    def test_an_arm_that_shows_a_schema_carries_it_whole(self):
        schema = {"type": "object", "properties": {"unit": {"type": "string"}}}
        content = build_messages(request(schema), arm("schema-dump-catalog-not-enforced-gated", ("Length",)))[0].content
        assert '"unit"' in content

    def test_the_gate_warning_appears_only_with_a_gate(self):
        assert any("discarded" in s for s in sections(arm("schema-dump-catalog-flat-enforced", ("Length",))))
        assert not any("discarded" in s for s in sections(arm("no-catalog-not-enforced")))


class TestThePropertyStepStatesBothCosts:
    """A step told only that omission is irreversible will include when unsure.

    Measured before this: 21 properties named that the document does not
    state against 6 missed. The prompt named the cost of leaving one out and
    no cost for putting one in, so the step did what it was told.
    """

    def _system(self) -> str:
        from oold.agent.prompts import build_property_messages

        messages = build_property_messages(ExtractionRequest(document="d"), {"e1": ("name", "award")})
        return messages[0].content

    def test_naming_one_too_many_has_a_stated_cost(self):
        system = self._system()
        assert "invented or left empty" in system

    def test_leaving_one_out_still_has_its_cost(self):
        assert "will not be asked for again" in self._system()

    def test_it_states_the_rule_the_corpus_applies(self):
        """Ground truth is a value whose spelling was found in the document.
        Six models asked a looser question answered it six different ways,
        which is a prompt that has not said what it wants."""
        system = self._system()
        assert "appears in the text, in some spelling of it" in system
        assert "would usually have, is not" in system


class TestThePropertyStepIsShownWhatTheNamesMean:
    """A vocabulary question cannot be answered by rewording the question.

    Measured over six models at n=100: recall 0.80 to 0.92 against precision
    0.52 to 0.58. The values are found and filed under the wrong slot, and a
    bare name does not say whether the gallery holding a painting is its
    contentLocation or its provider.
    """

    def _listing(self, **kwargs) -> str:
        from oold.agent.prompts import build_property_messages

        request = ExtractionRequest(document="d", **kwargs)
        return build_property_messages(request, {"e1": ("about", "name")})[0].content

    def test_a_description_is_shown_beside_its_property(self):
        listing = self._listing(property_text={"about": "The subject matter of an object."})
        assert "about: The subject matter of an object." in listing

    def test_a_property_with_no_description_is_still_offered(self):
        assert "\n  name" in self._listing(property_text={"about": "The subject matter."})

    def test_without_descriptions_the_names_stay_on_one_line(self):
        """The compact form is what every corpus without a vocabulary gets."""
        assert "e1: about, name" in self._listing()
