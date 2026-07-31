"""Shared fixtures for the validation test suite."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

DATA = Path(__file__).parent.parent / "data" / "oold"
BROKEN = DATA / "broken"
COMPLIANCE = DATA / "compliance"
REMOTE_CONTEXT = DATA / "remote_context"


@pytest.fixture
def data_dir() -> Path:
    """The committed slice of oold-schema's examples."""
    return DATA


@pytest.fixture
def broken_dir() -> Path:
    """Deliberately broken schemas, which prove the checks actually fire."""
    return BROKEN


@pytest.fixture
def compliance_dir() -> Path:
    return COMPLIANCE


@pytest.fixture
def remote_context_dir() -> Path:
    return REMOTE_CONTEXT


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch) -> Path:
    """Point the document and meta caches at a temporary directory.

    Without this a test could pick up a warm cache from a previous run, which would hide an
    offline-handling bug.
    """
    cache = tmp_path / "cache"
    monkeypatch.setenv("OOLD_CACHE_DIR", str(cache))
    return cache


@pytest.fixture
def resolver(tmp_path):
    """An offline resolver with a private cache, so tests never share state or hit the network."""
    from oold.validation.resolve import Resolver

    return Resolver(cache_dir=tmp_path / "documents", offline=True)


@pytest.fixture(scope="session")
def bundle():
    """The latest tracked meta-schema bundle."""
    from oold.validation.meta_store import resolve_selection

    return resolve_selection(["latest"], offline=True)[0]


@pytest.fixture
def loader(resolver, data_dir):
    from oold.validation.loader import DocumentLoader

    return DocumentLoader(resolver, directory=data_dir)


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def upstream_dir() -> Path | None:
    """A local oold-schema checkout, when OOLD_SCHEMA_DIR points at one.

    Used by the opt-in live parity tests. Returns None otherwise so they can skip.
    """
    raw = os.environ.get("OOLD_SCHEMA_DIR")
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None
