"""The descriptor binding's construction cost, measured as a ratio.

An absolute threshold cannot hold here: CI runners and this machine drift by
tens of percent between runs, and the absolutes differ by more than 2x between
runners. The ratio against plain pydantic is stable within one machine, 3.38x to
3.53x across repeated local runs, and stays under 9x across the whole CI matrix.

What it guards: pydantic 2.13 called ``inspect.signature`` on a private-attr
factory twice per attribute per construction, without caching. LinkedBaseModel
declares two, ``_links`` and ``_extra_iris``, so construction went to 17.8x
plain pydantic. ``pyproject.toml`` excludes that series; this fails if an
equivalent regression arrives through another dependency bump.

The descriptor binding is imported directly, so the check runs whatever
``OOLD_DESCRIPTOR_BINDING`` is set to. The legacy binding constructs an order of
magnitude slower by design and would need a threshold loose enough to measure
nothing.
"""

import timeit

from pydantic import BaseModel, ConfigDict

from oold.model._descriptor import LinkedBaseModel

MAX_RATIO = 15.0
"""Healthy runs measure 3.4x locally and up to 9.0x on CI; the 2.13 series
measures 17.8x locally and projects above 40x on the slower runners, because the
cost it adds is a fixed ~40 us per instance rather than a multiple. The spread
across runners is wider than it looks: plain pydantic construction is mostly
pydantic-core, which is fast everywhere, while the binding adds Python-level work
whose relative cost follows the interpreter. So the budget sits well above the
healthy ceiling rather than halfway."""

ROUNDS = 25
LOOPS = 500


class Plain(BaseModel):
    f0: str | None = None
    f1: str | None = None
    f2: str | None = None
    f3: str | None = None
    f4: str | None = None
    f5: str | None = None
    f6: str | None = None
    f7: str | None = None


class Linked(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"$id": "https://example.org/ConstructionCost"})
    f0: str | None = None
    f1: str | None = None
    f2: str | None = None
    f3: str | None = None
    f4: str | None = None
    f5: str | None = None
    f6: str | None = None
    f7: str | None = None


VALUES = {f"f{i}": "v" for i in range(8)}


def _microseconds(cls: type) -> float:
    return timeit.timeit(lambda: cls(**VALUES), number=LOOPS) / LOOPS * 1e6


def test_construction_stays_within_a_ratio_of_plain_pydantic():
    # Interleaved, so a frequency or scheduling dip lands on both models rather
    # than on whichever happens to be measured during it. The minimum of the
    # rounds is then the cleanest round each model got.
    plain, linked = [], []
    for _ in range(ROUNDS):
        plain.append(_microseconds(Plain))
        linked.append(_microseconds(Linked))

    fastest_plain, fastest_linked = min(plain), min(linked)
    ratio = fastest_linked / fastest_plain

    assert ratio < MAX_RATIO, (
        f"LinkedBaseModel construction is {ratio:.1f}x plain pydantic "
        f"({fastest_linked:.1f} us against {fastest_plain:.1f} us), over the {MAX_RATIO}x budget"
    )
