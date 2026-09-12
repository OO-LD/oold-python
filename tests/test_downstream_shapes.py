"""Declaration shapes that only appear in generated downstream packages.

Both are cases the shipped binding tolerates by accident and the descriptor
binding broke on the first real run against a generated package:

1. a subclass **redeclaring** an inherited link field - pydantic inspects the
   bases for a same-named attribute and rejects the field when it finds one, and
   the installed descriptor is exactly such an attribute;
2. a link field whose declared default is ``T.parse_obj("<iri>")`` - a default
   that can only ever raise, and which pydantic evaluates as soon as the link
   value is routed out of the payload.
"""

import pytest
from pydantic import Field
from pydantic.v1 import BaseModel as BaseModelV1
from pydantic.v1 import Field as FieldV1

from oold.model._descriptor import LinkedBaseModel
from oold.model.v1._descriptor import LinkedBaseModel as LinkedBaseModelV1


class Target(LinkedBaseModel):
    id: str | None = None
    label: str | None = None


class TargetV1(BaseModelV1):
    id: str | None = None
    label: str | None = None


def test_subclass_may_redeclare_a_link_field():
    class Base(LinkedBaseModel):
        id: str
        ref: Target | None = Field(None, json_schema_extra={"range": "Target"})

    class Derived(Base):
        # narrowing or re-annotating an inherited link is what generated
        # packages do whenever a subschema restates a property
        ref: Target | None = Field(None, json_schema_extra={"range": "Target"})

    d = Derived(id="ex:d", ref="ex:t")
    assert d.link_iris("ref") == "ex:t"


def test_subclass_may_redeclare_a_link_field_v1():
    class Base(LinkedBaseModelV1):
        id: str
        ref: TargetV1 | None = FieldV1(None, range="Target")

    class Derived(Base):
        ref: TargetV1 | None = FieldV1(None, range="Target")

    d = Derived(id="ex:d", ref="ex:t")
    assert d.link_iris("ref") == "ex:t"


def _explode(_cls):
    raise ValueError("a model cannot be parsed from an IRI string")


def test_link_field_default_is_never_evaluated():
    """The declared default is dead weight - the descriptor owns the value."""

    class M(LinkedBaseModel):
        id: str
        ref: Target = Field(
            default_factory=lambda: _explode(Target),
            json_schema_extra={"range": "Target"},
        )

    assert M(id="ex:m").link_iris("ref") is None  # unset, default not evaluated
    assert M(id="ex:m", ref="ex:t").link_iris("ref") == "ex:t"


def test_link_field_default_is_never_evaluated_v1():
    class M(LinkedBaseModelV1):
        id: str
        ref: TargetV1 = FieldV1(default_factory=lambda: _explode(TargetV1), range="Target")

    assert M(id="ex:m").link_iris("ref") is None
    assert M(id="ex:m", ref="ex:t").link_iris("ref") == "ex:t"


@pytest.mark.parametrize("base", [LinkedBaseModel, LinkedBaseModelV1])
def test_setattr_accepts_the_internal_flag(base):
    """``BaseController.__setattr__`` forwards ``internal=`` to the model."""
    field = Field if base is LinkedBaseModel else FieldV1
    extra = {"json_schema_extra": {"range": "Target"}} if base is LinkedBaseModel else {"range": "Target"}
    target = Target if base is LinkedBaseModel else TargetV1

    class M(base):
        id: str
        ref: target | None = field(None, **extra)

    m = M(id="ex:m")
    # internal=True writes the value as given, bypassing link handling
    m.__setattr__("id", "ex:other", internal=True)
    assert m.id == "ex:other"


def test_v1_to_json_encodes_non_json_types():
    """dict() leaves UUID/datetime as objects; to_json() must not."""
    import json
    from datetime import datetime, timezone
    from uuid import UUID

    class Doc(LinkedBaseModelV1):
        uuid: UUID
        at: datetime
        ref: TargetV1 | None = FieldV1(None, range="Target")

    doc = Doc(
        uuid=UUID("6dd0a5aa-8b53-4b0f-8a1d-2b1b1a1f0c11"),
        at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        ref="ex:t",
    )
    out = doc.to_json()
    assert out["uuid"] == "6dd0a5aa-8b53-4b0f-8a1d-2b1b1a1f0c11"
    assert out["ref"] == "ex:t"
    json.dumps(out)  # the whole point: the result is JSON-serialisable


def test_unset_links_honour_the_exclude_flags():
    """The unset-key was written after handler(), so it survived every
    exclusion - putting an explicit null into every stored document."""

    class M(LinkedBaseModel):
        id: str
        one: Target | None = Field(None, json_schema_extra={"range": "Target"})
        links: list[Target] | None = Field(None, json_schema_extra={"range": "Target"})

    M.model_rebuild()
    m = M(id="ex:m", one="ex:1")
    assert "links" not in m.to_json()
    assert "links" not in m.model_dump(exclude_none=True)
    assert "links" not in m.model_dump(exclude={"links"})
    assert m.model_dump()["links"] is None  # still there when nothing is excluded
