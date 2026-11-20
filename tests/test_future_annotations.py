"""Link declarations under ``from __future__ import annotations``.

The future import stringizes every annotation in the module, so the metaclass
default injection cannot see ``Link[...]`` as a type - it has to recognise the
source text, or a bare link field stays pydantic-required and construction
fails with a misleading "Field required" about a value that was supplied.
"""

from __future__ import annotations

import pytest

from oold.model._descriptor import Link, LinkedBaseModel, LinkList


class Org(LinkedBaseModel):
    id: str
    type: str | None = "fut:Org"


class Person(LinkedBaseModel):
    id: str
    type: str | None = "fut:Person"
    employer: Link[Org]
    knows: LinkList[Person] | None = None


Person.model_rebuild()


def test_a_bare_link_constructs_under_the_future_import():
    p = Person(id="fut:p", employer="fut:acme")
    assert p.link_iris("employer") == "fut:acme"


def test_requiredness_still_follows_the_annotation():
    with pytest.raises(ValueError, match="employer is required"):
        Person(id="fut:p")
    assert "employer" in (Person.export_schema().get("required") or [])
    assert "knows" not in (Person.export_schema().get("required") or [])
