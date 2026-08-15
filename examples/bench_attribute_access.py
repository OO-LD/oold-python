"""Where does the attribute-access cost of the shipped binding come from?

Decomposes the per-access overhead of ``oold.model.LinkedBaseModel`` into the
cost of *calling* a Python-level ``__getattribute__`` at all, versus the cost of
the *work* it does. This answers whether gating the interception on range
annotations (early-exit for non-link fields) would restore native performance.

Baselines cover plain pydantic v1 and v2, and both shipped ``LinkedBaseModel``
variants, so each binding is compared against its own pydantic version.

Run it:

    python examples/bench_attribute_access.py

Each variant runs in a **separate subprocess**: importing ``oold.model``
monkeypatches ``pydantic.fields.FieldInfo`` process-wide, which would otherwise
contaminate the plain-pydantic baselines measured in the same process.

Result (see docs/design/graph-object-binding.md section 2): gating removes most
but not all of the overhead, because a Python-level ``__getattribute__`` is
still invoked on every access. The descriptor binding reaches parity with plain
pydantic because the equivalent gate is performed by the C-level descriptor
protocol during normal attribute lookup.
"""

import subprocess
import sys
import timeit
from typing import Optional

N = 300_000
REP = 7


def build_plain_v2():
    from pydantic import BaseModel

    class M(BaseModel):
        id: str
        literal: Optional[str] = None

    return M(id="x", literal="v")


def build_plain_v1():
    from pydantic.v1 import BaseModel

    class M(BaseModel):
        id: str
        literal: Optional[str] = None

    return M(id="x", literal="v")


def build_gated_best():
    """Best case gate: closure frozenset, no attribute lookup on the fast path."""
    from pydantic import BaseModel

    links = frozenset({"link_a", "link_b"})

    class M(BaseModel):
        id: str
        literal: Optional[str] = None

        def __getattribute__(self, name):
            if name in links:
                pass  # slow path, not taken for plain fields
            return object.__getattribute__(self, name)

    return M(id="x", literal="v")


def build_gated_real():
    """Realistic gate: per-class set, needs a type(self) lookup on every access."""
    from pydantic import BaseModel

    class M(BaseModel):
        id: str
        literal: Optional[str] = None
        __link_names__ = frozenset({"link_a", "link_b"})

        def __getattribute__(self, name):
            if name in type(self).__link_names__:
                pass
            return object.__getattribute__(self, name)

    return M(id="x", literal="v")


def build_shipped_v2():
    from oold.model import LinkedBaseModel

    class M(LinkedBaseModel):
        id: str
        literal: Optional[str] = None

    return M(id="x", literal="v")


def build_shipped_v1():
    from oold.model.v1 import LinkedBaseModel

    class M(LinkedBaseModel):
        id: str
        literal: Optional[str] = None

    return M(id="x", literal="v")


def build_descriptor():
    from oold.experimental.descriptor_binding import LinkedModel, LinkList

    class M(LinkedModel):
        id: str
        literal: Optional[str] = None
        links = LinkList["M"]("M")

    return M(id="x", literal="v")


def build_auto_descriptor():
    """Auto-installed descriptors: unchanged declaration syntax."""
    from typing import List

    from pydantic import Field

    from oold.experimental.auto_descriptor_binding import AutoLinkedModel

    class M(AutoLinkedModel):
        id: str
        literal: Optional[str] = None
        links: Optional[List["M"]] = Field(
            None, json_schema_extra={"x-oold-range": "M"}
        )

    M.model_rebuild()
    return M(id="x", literal="v")


VARIANTS = {
    "plain_v1": ("plain pydantic v1 (baseline v1)", build_plain_v1),
    "plain_v2": ("plain pydantic v2 (baseline v2)", build_plain_v2),
    "gated_best": ("gated __getattribute__ (best case)", build_gated_best),
    "gated_real": ("gated __getattribute__ (realistic)", build_gated_real),
    "shipped_v1": ("shipped LinkedBaseModel v1", build_shipped_v1),
    "shipped_v2": ("shipped LinkedBaseModel v2", build_shipped_v2),
    "descriptor": ("descriptor binding (v2)", build_descriptor),
    "auto_descriptor": ("auto-descriptor, syntax unchanged", build_auto_descriptor),
}


def measure(key: str) -> float:
    obj = VARIANTS[key][1]()
    return min(timeit.repeat(lambda: obj.literal, number=N, repeat=REP))


def main() -> None:
    results = {}
    for key in VARIANTS:
        out = subprocess.run(
            [sys.executable, __file__, key], capture_output=True, text=True
        )
        if out.returncode != 0:
            print(f"{key}: FAILED\n{out.stderr[-600:]}")
            continue
        results[key] = float(out.stdout.strip())

    b1 = results.get("plain_v1")
    b2 = results.get("plain_v2")
    print(f"plain-field access, {N:,}x, best of {REP}, each in its own process\n")
    print(f"{'variant':40} {'time':>9} {'vs v1':>8} {'vs v2':>8}")
    for key, t in results.items():
        label = VARIANTS[key][0]
        r1 = f"{t / b1:6.2f}x" if b1 else "      na"
        r2 = f"{t / b2:6.2f}x" if b2 else "      na"
        print(f"{label:40} {t * 1e3:7.1f}ms {r1:>8} {r2:>8}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(measure(sys.argv[1]))
    else:
        main()
