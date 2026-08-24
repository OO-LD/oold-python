"""Benchmark every graph-object binding variant across every hot operation.

Operations measured: plain-field read, plain-field write, linked-field read
(warm, already resolved), linked-field write, and query construction
(``Cls.field == value``).

Each variant runs in a **separate subprocess**: importing ``oold.model``
monkeypatches ``pydantic.fields.FieldInfo`` process-wide and would otherwise
contaminate the plain-pydantic baselines measured in the same process.

Run it:

    python examples/bench_binding_variants.py
"""

import subprocess
import sys
import timeit

N = 100_000
REP = 5


def build_plain_v1():
    from pydantic.v1 import BaseModel

    class M(BaseModel):
        id: str
        literal: str | None = None

    return M(id="x", literal="v"), M, None, None


def build_plain_v2():
    from pydantic import BaseModel

    class M(BaseModel):
        id: str
        literal: str | None = None

    return M(id="x", literal="v"), M, None, None


def build_gated():
    """Hypothetical: current design with the interception gated on link names."""
    from pydantic import BaseModel

    links = frozenset({"link"})

    class M(BaseModel):
        id: str
        literal: str | None = None

        def __getattribute__(self, name):
            if name in links:
                pass  # slow path, not taken for plain fields
            return object.__getattribute__(self, name)

    return M(id="x", literal="v"), M, None, None


def build_shipped_v1():
    from pydantic.v1 import Field as F1

    from oold.model.v1 import LinkedBaseModel

    class T(LinkedBaseModel):
        id: str

    class M(LinkedBaseModel):
        id: str
        literal: str | None = None
        link: T | None = F1(None, range="T")

    obj = M(id="x", literal="v", link=T(id="ex:t"))
    _ = obj.link
    return obj, M, "link", T(id="ex:t2")


def build_shipped_v2():
    from pydantic import Field

    from oold.model import LinkedBaseModel

    class T(LinkedBaseModel):
        id: str

    class M(LinkedBaseModel):
        id: str
        literal: str | None = None
        link: T | None = Field(None, json_schema_extra={"range": "T"})

    obj = M(id="x", literal="v", link=T(id="ex:t"))
    _ = obj.link
    return obj, M, "link", T(id="ex:t2")


def build_auto_implicit():
    """Auto-descriptor, implicit form: annotated field + range keyword."""
    from oold.model._descriptor import AutoLinkedModel, OoldField

    class T(AutoLinkedModel):
        id: str

    class M(AutoLinkedModel):
        id: str
        literal: str | None = None
        link: T | None = OoldField(default=None, range="T")

    M.model_rebuild()
    obj = M(id="x", literal="v", link=T(id="ex:t"))
    _ = obj.link
    return obj, M, "link", T(id="ex:t2")


def build_auto_explicit():
    """Auto-descriptor, explicit form: descriptor declared in the class body."""
    from oold.model._descriptor import AutoLinkedModel, Link

    class T(AutoLinkedModel):
        id: str

    class M(AutoLinkedModel):
        id: str
        literal: str | None = None
        link = Link(T)

    obj = M(id="x", literal="v", link=T(id="ex:t"))
    _ = obj.link
    return obj, M, "link", T(id="ex:t2")


def build_ref():
    """Explicit Ref[T] wrapper."""
    from oold.model._ref import OoldModel, Ref

    class T(OoldModel):
        id: str

    class M(OoldModel):
        id: str
        literal: str | None = None
        link: Ref[T] | None = None

    obj = M(id="x", literal="v", link=T(id="ex:t"))
    _ = obj.link
    return obj, M, "link", T(id="ex:t2")


VARIANTS = {
    "plain_v1": ("plain pydantic v1", build_plain_v1),
    "plain_v2": ("plain pydantic v2", build_plain_v2),
    "gated": ("gated __getattribute__", build_gated),
    "shipped_v1": ("shipped LinkedBaseModel v1", build_shipped_v1),
    "shipped_v2": ("shipped LinkedBaseModel v2", build_shipped_v2),
    "auto_implicit": ("auto-descriptor (implicit)", build_auto_implicit),
    "auto_explicit": ("auto-descriptor (explicit)", build_auto_explicit),
    "ref": ("explicit Ref[T]", build_ref),
}

OPS = ["plain_read", "plain_write", "link_read", "link_write", "query"]


def measure(key: str) -> dict:
    obj, cls, linkname, linkval = VARIANTS[key][1]()
    out = {}
    out["plain_read"] = min(timeit.repeat(lambda: obj.literal, number=N, repeat=REP))

    def setp():
        obj.literal = "v"

    out["plain_write"] = min(timeit.repeat(setp, number=N, repeat=REP))

    if linkname:
        out["link_read"] = min(timeit.repeat(lambda: getattr(obj, linkname), number=N, repeat=REP))

        def setl():
            setattr(obj, linkname, linkval)

        try:
            out["link_write"] = min(timeit.repeat(setl, number=N, repeat=REP))
        except Exception:
            out["link_write"] = None
    try:
        out["query"] = min(timeit.repeat(lambda: cls.literal == "John", number=N, repeat=REP))
    except Exception:
        out["query"] = None
    return out


def main() -> None:
    results = {}
    for key in VARIANTS:
        proc = subprocess.run([sys.executable, __file__, key], capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"{key}: FAILED\n{proc.stderr[-500:]}\n")
            continue
        results[key] = eval(proc.stdout.strip())  # noqa: S307

    base = results.get("plain_v2", {}).get("plain_read")
    print(f"\n{N:,}x per op, best of {REP}, isolated processes")
    print("times in ms; (x) = relative to plain pydantic v2 plain-read\n")
    head = f"{'variant':28}" + "".join(f"{o:>16}" for o in OPS)
    print(head)
    print("-" * len(head))
    for key, vals in results.items():
        row = f"{VARIANTS[key][0]:28}"
        for op in OPS:
            t = vals.get(op)
            if t is None:
                row += f"{'na':>16}"
            else:
                row += f"{t * 1e3:8.1f}({t / base:4.1f}x)"
        print(row)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(repr(measure(sys.argv[1])))
    else:
        main()
