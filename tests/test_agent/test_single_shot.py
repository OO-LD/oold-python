class TestAnAnswerWithNoPlanStillNamesItsEntities:
    """An entity that names itself nothing cannot be pointed at.

    Measured on one recipe page: a single call returned 43 entities, every
    one correctly typed as a HowToStep, HowToSupply or HowToSection, not one
    carrying an id and not a single link between them. An id the schema
    leaves optional is an id a long answer drops.
    """

    def _schema(self):
        return {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"type": {"type": "string"}, "name": {"type": "string"}},
                    },
                }
            },
        }

    def _prepared(self, orchestration):
        from oold.agent.enforcement import ARMS
        from oold.agent.extraction import ExtractionAgent, ExtractionRequest, _entity_shapes
        from oold.agent.provider import profile_for

        agent = ExtractionAgent(
            _Silent(), ARMS["schema-dump-catalog-flat-enforced"], profile_for("openai"), orchestration=orchestration
        )
        request = ExtractionRequest(document="d", schema=self._schema())
        prepared, _, _, _ = agent._schema_for(request, (), ())
        return _entity_shapes(prepared)[0]

    def test_the_id_is_required_with_no_plan_to_pin_it_to(self):
        from oold.agent.enforcement import Orchestration

        shape = self._prepared(Orchestration.SINGLE_SHOT)
        assert "id" in shape["properties"]
        assert "id" in shape["required"]

    def test_it_carries_no_enum_where_no_plan_issued_the_ids(self):
        from oold.agent.enforcement import Orchestration

        shape = self._prepared(Orchestration.SINGLE_SHOT)
        assert "enum" not in shape["properties"]["id"]
        assert shape["properties"]["id"]["type"] == "string"

    def test_the_model_is_asked_for_the_id_the_plan_step_is_not_asked_for(self):
        """There is no plan step here to assign one from, and an entity still
        has to name itself before another can point at it. The plan step is
        asked for neither, because it issues the keys itself."""
        from oold.agent.enforcement import Orchestration
        from oold.agent.prompts import selection_schema

        shape = self._prepared(Orchestration.SINGLE_SHOT)
        planned = selection_schema(("Person",), 3)["properties"]["entities"]["items"]
        assert shape["properties"]["id"]["description"]
        assert "id" not in planned["properties"]


class _Silent:
    model = "silent"

    def invoke(self, messages, *, response_format=None, strict=False):
        from oold.agent.client import ChatResponse

        return ChatResponse(text="{}", parsed={}, usage=None, raw=None)
