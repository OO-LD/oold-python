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

    from typing import Optional

    class Foo(LinkedBaseModel):
        value: float
        label: Optional[str] = None

    obj = Foo(value=1.0)
    result = obj.to_json()
    assert "label" not in result
