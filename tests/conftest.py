"""Shared fixtures.

Two registries here are process-wide: resolvers (an unregistered prefix falls
back to whatever else is in it) and the type registry (keyed by type IRI, so two
modules using the same ``type`` default shadow each other). Both have broken a
run already, which is why the fixtures below always restore.
"""

import importlib.util

import pytest

from oold.backend import interface
from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import SetResolverParam, set_resolver


@pytest.fixture
def linked_store():
    """Register a document store for a prefix, and take it out again after.

    Usage::

        def test_x(linked_store):
            store = linked_store("ex", {"ex:1": {"id": "ex:1", "type": "ex:T"}})
    """
    saved = dict(interface._resolvers)

    def _make(prefix: str, docs: dict | None = None) -> SimpleDictDocumentStore:
        store = SimpleDictDocumentStore()
        if docs:
            store.store_json_dicts(docs)
        set_resolver(SetResolverParam(iri=prefix, resolver=store))
        return store

    yield _make
    interface._resolvers.clear()
    interface._resolvers.update(saved)


@pytest.fixture(autouse=True)
def _restore_global_registries():
    """Undo what a *test* registers, in both process-wide registries.

    Restoring the resolvers alone was not enough: the type registry is keyed by
    type IRI, and with the descriptor binding as the default it is the same dict
    as ``oold.model._types``. Two modules declaring a class with the same
    ``type`` default therefore overwrite each other, and which one wins depends
    on collection order - running the suite in reverse produced three failures.

    Classes registered at *module import* are left alone: they are set up before
    this fixture runs, so the snapshot already contains them.
    """
    from oold.model import _descriptor, _types
    from oold.model.v1 import _descriptor as _descriptor_v1

    registries = [interface._resolvers, _types, _descriptor._TYPE_REGISTRY, _descriptor_v1._TYPE_REGISTRY]
    saved = [dict(r) for r in registries]
    yield
    for registry, snapshot in zip(registries, saved, strict=True):
        registry.clear()
        registry.update(snapshot)


def pytest_configure(config):
    """Register the ``benchmark`` mark so it is not an unknown-mark warning."""
    config.addinivalue_line("markers", "benchmark(**kwargs): pytest-benchmark group settings")


if not importlib.util.find_spec("pytest_benchmark"):

    @pytest.fixture
    def benchmark():
        """Run the function once when pytest-benchmark is not installed.

        Without it every test taking this fixture *errors out* rather than
        failing, and an error is easy to read as environmental. Two real
        regressions sat behind those errors until CI - which does have the
        plugin - ran them. Locally the timing is worthless, but the assertions
        around it are the point.
        """

        def _run(func, *args, **kwargs):
            return func(*args, **kwargs)

        return _run
