"""Tests for to_json / from_json serialization."""

import pytest


def _get_models(pydantic_version):
    if pydantic_version == "v2":
        from oold.model import LinkedBaseModel
    else:
        from oold.model.v1 import LinkedBaseModel
    return LinkedBaseModel


@pytest.mark.parametrize("pydantic_version", ["v1", "v2"])
def test_to_json_returns_dict(pydantic_version):
    LinkedBaseModel = _get_models(pydantic_version)

    class Foo(LinkedBaseModel):
        value: float
        name: str = "default"

    obj = Foo(value=42.0)
    result = obj.to_json()
    assert isinstance(result, dict)
    assert result["value"] == 42.0
    assert result["name"] == "default"


@pytest.mark.parametrize("pydantic_version", ["v1", "v2"])
def test_to_json_exclude_defaults(pydantic_version):
    LinkedBaseModel = _get_models(pydantic_version)

    class Foo(LinkedBaseModel):
        value: float
        name: str = "default"

    obj = Foo(value=42.0)
    result = obj.to_json(exclude_defaults=True)
    assert "value" in result
    assert "name" not in result


@pytest.mark.parametrize("pydantic_version", ["v1", "v2"])
def test_from_json_restores_defaults(pydantic_version):
    LinkedBaseModel = _get_models(pydantic_version)

    class Foo(LinkedBaseModel):
        value: float
        name: str = "default"

    compact = {"value": 42.0}
    restored = Foo.from_json(compact)
    assert restored.value == 42.0
    assert restored.name == "default"


@pytest.mark.parametrize("pydantic_version", ["v1", "v2"])
def test_to_json_exclude_defaults_false(pydantic_version):
    LinkedBaseModel = _get_models(pydantic_version)

    class Foo(LinkedBaseModel):
        value: float
        name: str = "default"

    obj = Foo(value=42.0)
    full = obj.to_json(exclude_defaults=False)
    assert full["name"] == "default"
    assert full["value"] == 42.0


@pytest.mark.parametrize("pydantic_version", ["v1", "v2"])
def test_to_json_excludes_none(pydantic_version):
    LinkedBaseModel = _get_models(pydantic_version)

    class Foo(LinkedBaseModel):
        value: float
        label: str | None = None

    obj = Foo(value=1.0)
    result = obj.to_json()
    assert "label" not in result


def _model_with_a_link_default(pydantic_version, tag):
    """A model whose link declares a default IRI, spelled as each version does.

    Imports the descriptor bindings directly rather than through
    ``oold.model``: the legacy bindings do not record a link's declared default
    at all, so what is asserted here would depend on OOLD_DESCRIPTOR_BINDING.
    """
    if pydantic_version == "v2":
        from oold.model._descriptor import Link, LinkedBaseModel, OoldField

        class Org(LinkedBaseModel):
            id: str
            type: str | None = f"ex:{tag}Org"

        class Person(LinkedBaseModel):
            id: str
            type: str | None = f"ex:{tag}Person"
            employer: Link[Org | None] = OoldField(default="ex:default-org")
            mentor: Link[Org | None] = OoldField()

        return Person

    from pydantic.v1 import Field

    from oold.model.v1._descriptor import LinkedBaseModel

    class Org(LinkedBaseModel):
        id: str
        type: str | None = f"ex:{tag}Org"

    class Person(LinkedBaseModel):
        id: str
        type: str | None = f"ex:{tag}Person"
        employer: Org | None = Field("ex:default-org", range="Org")
        mentor: Org | None = Field(None, range="Org")

    return Person


@pytest.mark.parametrize("pydantic_version", ["v1", "v2"])
def test_exclude_defaults_omits_a_link_left_at_its_declared_default(pydantic_version):
    """A link is declared with a default IRI, so a value equal to it is a default.

    The binding routes link values out of the payload pydantic validates, so the
    field always sits at None there and pydantic's own comparison cannot see
    this. The declared IRI is kept in ``__link_defaults__`` and compared against.
    """
    Person = _model_with_a_link_default(pydantic_version, "D")

    result = Person(id="ex:p").to_json(exclude_defaults=True)

    assert "employer" not in result, result
    assert result["id"] == "ex:p"


@pytest.mark.parametrize("pydantic_version", ["v1", "v2"])
def test_exclude_defaults_keeps_a_link_set_to_another_iri(pydantic_version):
    Person = _model_with_a_link_default(pydantic_version, "K")

    result = Person(id="ex:p", employer="ex:acme").to_json(exclude_defaults=True)

    assert result["employer"] == "ex:acme", result


@pytest.mark.parametrize("pydantic_version", ["v1", "v2"])
def test_exclude_defaults_omits_a_link_that_was_never_set(pydantic_version):
    """An unset link is at its default, and the key is re-added after the
    handler has applied the exclusions - so it has to be skipped there too."""
    Person = _model_with_a_link_default(pydantic_version, "U")
    person = Person(id="ex:p")
    dump = person.model_dump if pydantic_version == "v2" else person.dict

    result = dump(exclude_defaults=True)

    assert "mentor" not in result, result
