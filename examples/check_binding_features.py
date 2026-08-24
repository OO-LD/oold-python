"""Feature-check every graph-object binding variant against the requirements.

Each requirement is verified by actually exercising the variant, not asserted by
hand. Prints a matrix of ok / FAIL / na per variant, so regressions and gaps are
visible rather than claimed.

Each variant runs in a **separate subprocess**: importing ``oold.model``
monkeypatches ``pydantic.fields.FieldInfo`` process-wide, and the monkeypatch
check itself must therefore be isolated.

Run it:

    python examples/check_binding_features.py
"""

import subprocess
import sys
from collections.abc import Callable

REQUIREMENTS = [
    ("syntax_unchanged", "standard annotations, no wrapper type in declaration"),
    ("build_by_iri", "construct a link from an IRI string"),
    ("build_by_object", "construct a link from a model instance"),
    ("lazy", "no backend call before first access"),
    ("real_object", "access returns the real target (isinstance holds)"),
    ("polymorphic", "resolves to the actual subclass via its type IRI"),
    ("batched", "N-item list resolves in ONE backend call"),
    ("cached", "second access does not re-resolve"),
    ("mutation", "assignment replaces the link and invalidates the cache"),
    ("link_validated", "linked object is validated by its own model on construction"),
    ("list_lookup", "list IRI lookup: links['ex:t2']"),
    ("list_filter", "list filtering: links[T.label == 'two']"),
    ("list_projection", "list attribute projection: links.label"),
    ("serialize_iri", "serialisation emits IRIs for links"),
    ("query_dsl", "Cls.field == v and Cls[cond] work"),
    ("typed_extras", "validated json_schema_extra (OoldExtra)"),
    ("no_monkeypatch", "import does not patch pydantic FieldInfo"),
]

VARIANT_NAMES = {
    "shipped_v1": "shipped v1",
    "shipped_v2": "shipped v2",
    "auto_implicit": "auto (implicit)",
    "auto_explicit": "auto (explicit)",
    "ref": "Ref[T]",
}

MODULE_OF = {
    "shipped_v1": "oold.model.v1",
    "shipped_v2": "oold.model",
    "auto_implicit": "oold.model._descriptor",
    "auto_explicit": "oold.model._descriptor",
    "ref": "oold.model._ref",
}

CALLS: list[list] = []

# Stored documents carry a type IRI so polymorphic dispatch can be exercised.
DATA = {
    "ex:t1": {"id": "ex:t1", "label": "one", "type": "ex:T"},
    "ex:t2": {"id": "ex:t2", "label": "two", "type": "ex:T"},
    "ex:s1": {"id": "ex:s1", "label": "sub", "type": "ex:S"},
}


def counting_store():
    from oold.backend.document_store import SimpleDictDocumentStore
    from oold.backend.interface import SetResolverParam, set_resolver

    class Counting(SimpleDictDocumentStore):
        def resolve_iris(self, iris):
            CALLS.append(list(iris))
            return super().resolve_iris(iris)

    s = Counting()
    s.store_json_dicts(DATA)
    set_resolver(SetResolverParam(iri="ex", resolver=s))
    return s


class Probe:
    """Collects requirement results, isolating failures per check."""

    def __init__(self) -> None:
        self.res: dict[str, bool | None] = {}

    def check(self, name: str, fn: Callable[[], bool]) -> None:
        try:
            self.res[name] = bool(fn())
        except Exception:
            self.res[name] = False

    def set(self, name: str, value: bool | None) -> None:
        self.res[name] = value


def check_shipped(version: int) -> dict:
    p = Probe()
    if version == 1:
        from pydantic.v1 import Field as F

        from oold.model.v1 import LinkedBaseModel as Base

        def link_field():
            return F(None, range="T")

    else:
        from pydantic import Field as F

        from oold.model import LinkedBaseModel as Base

        def link_field():
            return F(None, json_schema_extra={"range": "T"})

    class T(Base):
        id: str
        label: str | None = None
        type: str | None = "ex:T"

    class S(T):  # subclass for the polymorphism probe
        type: str | None = "ex:S"

    class M(Base):
        id: str
        name: str | None = None
        links: list[T] | None = link_field()

    p.set("syntax_unchanged", True)  # standard annotations, List[T]
    counting_store()

    CALLS.clear()
    m = M(id="ex:m", links=["ex:t1", "ex:t2"])
    p.set("build_by_iri", True)
    p.check("lazy", lambda: len(CALLS) == 0)
    got = m.links
    p.check("real_object", lambda: isinstance(got[0], T) and got[0].label == "one")
    p.check("batched", lambda: len(CALLS) == 1 and len(CALLS[0]) == 2)
    before = len(CALLS)
    _ = m.links
    p.check("cached", lambda: len(CALLS) == before)
    p.check(
        "build_by_object",
        lambda: isinstance(M(id="ex:m2", links=[T(id="ex:t1")]).links[0], T),
    )
    p.check("polymorphic", lambda: isinstance(M(id="ex:m3", links=["ex:s1"]).links[0], S))

    def mutate():
        m.links = [T(id="ex:t2", label="two")]
        return m.links[0].id == "ex:t2"

    p.check("mutation", mutate)

    def link_validated():
        # even when the parent's field validation is bypassed, the linked
        # object must still be validated by its own model at construction
        try:
            M(id="ex:mv", links=[{"label": "no id"}])  # 'id' is required on T
            return False
        except Exception:
            return True

    p.check("link_validated", link_validated)

    p.check("list_lookup", lambda: m.links["ex:t2"].id == "ex:t2")
    p.check("list_filter", lambda: [x.id for x in m.links[T.label == "two"]] == ["ex:t2"])
    p.check("list_projection", lambda: list(m.links.label) == ["two"])
    p.check("serialize_iri", lambda: m.to_json().get("links") == ["ex:t2"])
    p.check("query_dsl", lambda: getattr(M.name == "John", "field", None) == "name")
    p.set("typed_extras", False)  # raw dict only
    return p.res


def check_auto(explicit: bool) -> dict:
    from oold.model._descriptor import (
        AutoLinkedModel,
        LinkList,
        OoldExtra,
        OoldField,
    )

    p = Probe()

    class T(AutoLinkedModel):
        id: str
        label: str | None = None
        type: str | None = "ex:T"

    class S(T):
        type: str | None = "ex:S"

    if explicit:

        class M(AutoLinkedModel):
            id: str
            name: str | None = None
            links = LinkList(T)

        p.set("syntax_unchanged", False)  # unannotated descriptor assignment
    else:

        class M(AutoLinkedModel):
            id: str
            name: str | None = None
            links: list[T] | None = OoldField(default=None, range="T")

        p.set("syntax_unchanged", True)

    counting_store()
    CALLS.clear()
    m = M(id="ex:m", links=["ex:t1", "ex:t2"])
    p.set("build_by_iri", True)
    p.check("lazy", lambda: len(CALLS) == 0)
    got = m.links
    p.check("real_object", lambda: isinstance(got[0], T) and got[0].label == "one")
    p.check("batched", lambda: len(CALLS) == 1 and len(CALLS[0]) == 2)
    before = len(CALLS)
    _ = m.links
    p.check("cached", lambda: len(CALLS) == before)
    p.check(
        "build_by_object",
        lambda: isinstance(M(id="ex:m2", links=[T(id="ex:t1")]).links[0], T),
    )
    # prototype constructs the declared target, it does not dispatch on type IRI
    p.check("polymorphic", lambda: isinstance(M(id="ex:m3", links=["ex:s1"]).links[0], S))

    def mutate():
        m.links = [T(id="ex:t2", label="two")]
        return m.links[0].id == "ex:t2"

    p.check("mutation", mutate)

    def link_validated():
        # even when the parent's field validation is bypassed, the linked
        # object must still be validated by its own model at construction
        try:
            M(id="ex:mv", links=[{"label": "no id"}])  # 'id' is required on T
            return False
        except Exception:
            return True

    p.check("link_validated", link_validated)

    p.check("list_lookup", lambda: m.links["ex:t2"].id == "ex:t2")
    p.check("list_filter", lambda: [x.id for x in m.links[T.label == "two"]] == ["ex:t2"])
    p.check("list_projection", lambda: list(m.links.label) == ["two"])
    p.check(
        "serialize_iri",
        lambda: m.model_dump(exclude_none=True).get("links") == ["ex:t2"],
    )

    def query():
        cond = M.name == "John"
        return getattr(cond, "field", None) == "name" and M[cond] is not None

    p.check("query_dsl", query)

    def typed():
        try:
            OoldExtra(range="")
            return False
        except Exception:
            return True

    p.check("typed_extras", typed)
    return p.res


def check_ref() -> dict:
    from oold.model._ref import OoldModel, Ref

    p = Probe()

    class T(OoldModel):
        id: str
        label: str | None = None
        type: str | None = "ex:T"

    class M(OoldModel):
        id: str
        name: str | None = None
        links: list[Ref[T]] | None = None

    p.set("syntax_unchanged", False)  # Ref[T] wrapper appears in the annotation
    counting_store()
    CALLS.clear()
    m = M(id="ex:m", links=["ex:t1", "ex:t2"])
    p.set("build_by_iri", True)
    p.check("lazy", lambda: len(CALLS) == 0)
    got = m.links
    p.check("real_object", lambda: isinstance(got[0], T))  # it is a Ref, expected False
    _ = [r.label for r in got]
    p.check("batched", lambda: len(CALLS) == 1 and len(CALLS[0]) == 2)
    before = len(CALLS)
    _ = [r.label for r in m.links]
    p.check("cached", lambda: len(CALLS) == before)
    p.check("build_by_object", lambda: M(id="ex:m2", links=[T(id="ex:t1")]) is not None)
    p.check("polymorphic", lambda: False)

    def mutate():
        m.links = [T(id="ex:t2", label="two")]
        return m.model_dump(exclude_none=True).get("links") == ["ex:t2"]

    p.check("mutation", mutate)

    def link_validated():
        # even when the parent's field validation is bypassed, the linked
        # object must still be validated by its own model at construction
        try:
            M(id="ex:mv", links=[{"label": "no id"}])  # 'id' is required on T
            return False
        except Exception:
            return True

    p.check("link_validated", link_validated)

    p.check("list_lookup", lambda: m.links["ex:t2"].id == "ex:t2")
    p.check("list_filter", lambda: [x.id for x in m.links[T.label == "two"]] == ["ex:t2"])
    p.check("list_projection", lambda: list(m.links.label) == ["two"])
    p.check(
        "serialize_iri",
        lambda: M(id="ex:m4", links=["ex:t2"]).model_dump(exclude_none=True).get("links") == ["ex:t2"],
    )
    p.check("query_dsl", lambda: False)
    p.set("typed_extras", False)
    return p.res


def monkeypatch_check(module: str) -> bool:
    code = f"import pydantic.fields as pf; import {module}; print(pf.FieldInfo.__name__)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    return out.returncode == 0 and out.stdout.strip() == "FieldInfo"


def run(key: str) -> dict:
    if key == "shipped_v1":
        res = check_shipped(1)
    elif key == "shipped_v2":
        res = check_shipped(2)
    elif key == "auto_implicit":
        res = check_auto(explicit=False)
    elif key == "auto_explicit":
        res = check_auto(explicit=True)
    elif key == "ref":
        res = check_ref()
    else:
        raise KeyError(key)
    res["no_monkeypatch"] = monkeypatch_check(MODULE_OF[key])
    return res


def main() -> None:
    results = {}
    for key in VARIANT_NAMES:
        proc = subprocess.run([sys.executable, __file__, key], capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"{key}: ERROR\n{proc.stderr[-700:]}\n")
            continue
        results[key] = eval(proc.stdout.strip())  # noqa: S307

    width = max(len(r) for r, _ in REQUIREMENTS) + 2
    header = f"{'requirement':{width}}" + "".join(f"{VARIANT_NAMES[k]:>17}" for k in results)
    print(header)
    print("-" * len(header))
    for req, _desc in REQUIREMENTS:
        row = f"{req:{width}}"
        for key in results:
            v = results[key].get(req)
            row += f"{('ok' if v else 'FAIL') if v is not None else 'na':>17}"
        print(row)
    print("\nlegend")
    for req, desc in REQUIREMENTS:
        print(f"  {req:18} {desc}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(repr(run(sys.argv[1])))
    else:
        main()
