"""The opt-in descriptor binding must keep downstream contracts intact.

``OOLD_DESCRIPTOR_BINDING=1`` swaps ``LinkedBaseModel`` for the descriptor
implementation. Two names have to move with it, because downstream imports them
and depends on their identity (see docs/design/downstream-migration.md):

* ``LinkedBaseModelMetaClass`` is subclassed downstream, so a derived metaclass
  must stay a subclass of whatever ``LinkedBaseModel`` actually uses - otherwise
  the import fails outright with a metaclass conflict;
* ``_types`` is written to downstream, so the binding must share that very
  mapping instead of keeping its own - otherwise resolution silently falls back
  to the declared target.

Each case runs in a subprocess: the switch is read at import time.
"""

import subprocess
import sys
import textwrap

REPRO = textwrap.dedent(
    """
    import warnings; warnings.filterwarnings("ignore")
    from oold.model import LinkedBaseModel, LinkedBaseModelMetaClass as ModelMetaclass
    import oold.model as m

    hook_ran = {}

    # verbatim downstream shape: a custom metaclass subclassing oold's, then a
    # model combining it with a LinkedBaseModel subclass
    class QuantityValueMetaclass(ModelMetaclass):
        def __new__(mcs, name, bases, namespace, **kwargs):
            cls = super().__new__(mcs, name, bases, namespace, **kwargs)
            hook_ran[name] = True
            return cls

    class OswLike(LinkedBaseModel):
        id: str

    class QuantityValue(OswLike, metaclass=QuantityValueMetaclass):
        pass

    print("BASE", LinkedBaseModel.__name__)
    print("HOOK", hook_ran.get("QuantityValue", False))
    print("METACLASS_MATCHES", isinstance(QuantityValue, type(LinkedBaseModel)))
    print("REGISTRY_IS_TYPES", m.registered_types() is m._types)
    """
)


def run(enabled: bool) -> dict:
    import os

    env = dict(os.environ)
    env["OOLD_DESCRIPTOR_BINDING"] = "1" if enabled else "0"
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", REPRO], capture_output=True, text=True, env=env
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return dict(line.split(" ", 1) for line in proc.stdout.strip().splitlines() if " " in line)


def test_default_keeps_the_shipped_binding():
    out = run(enabled=False)
    assert out["BASE"] == "LinkedBaseModel"


def test_switch_selects_the_descriptor_binding():
    out = run(enabled=True)
    assert out["BASE"] == "AutoLinkedModel"


def test_downstream_metaclass_subclassing_survives_the_switch():
    """The blocker: swapping only the base class breaks this with a conflict."""
    for enabled in (False, True):
        out = run(enabled=enabled)
        assert out["METACLASS_MATCHES"] == "True", enabled
        assert out["HOOK"] == "True", enabled  # the custom hook still runs


def test_registry_identity_is_preserved_either_way():
    for enabled in (False, True):
        assert run(enabled=enabled)["REGISTRY_IS_TYPES"] == "True", enabled


PLAIN = textwrap.dedent(
    """
    import warnings; warnings.filterwarnings("ignore")
    from pydantic import Field
    from oold.model import LinkedBaseModel

    class T(LinkedBaseModel):
        id: str
        label: str | None = None

    class M(LinkedBaseModel):
        id: str
        links: list[T] | None = Field(None, json_schema_extra={"range": "T"})

    M.model_rebuild()
    m = M(id="ex:m", links=[T(id="ex:t1", label="one")])
    print("DUMP", m.model_dump(exclude_none=True)["links"])
    print("DESCRIPTORS", bool(getattr(M, "__link_fields__", {})))
    """
)


def run_plain(links: str) -> dict:
    import os

    env = dict(os.environ)
    env["OOLD_DESCRIPTOR_BINDING"] = "1"
    env["OOLD_LINKS"] = links
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", PLAIN], capture_output=True, text=True, env=env
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return dict(line.split(" ", 1) for line in proc.stdout.strip().splitlines() if " " in line)


def test_links_on_collapse_to_iris():
    out = run_plain("1")
    assert out["DUMP"] == "['ex:t1']"
    assert out["DESCRIPTORS"] == "True"


def test_links_off_is_plain_pydantic():
    """OOLD_LINKS=0 turns a model back into plain pydantic, unedited."""
    out = run_plain("0")
    assert out["DUMP"] == "[{'id': 'ex:t1', 'label': 'one'}]"  # nested, not an IRI
    assert out["DESCRIPTORS"] == "False"  # nothing installed
