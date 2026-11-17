from pathlib import Path

import pytest

HERE = Path(__file__).parent
RDFLIB_NOISE = "ignore:ConjunctiveGraph is deprecated:DeprecationWarning"


def pytest_collection_modifyitems(config, items):
    """Silence rdflib's deprecation noise here, and skip ``scaling`` tests unless selected with ``-m scaling``."""
    selected = "scaling" in (config.getoption("-m") or "")
    skip = pytest.mark.skip(reason="slow, run with `pytest -m scaling`")
    for item in items:
        if not item.path.is_relative_to(HERE):
            continue
        item.add_marker(pytest.mark.filterwarnings(RDFLIB_NOISE))
        if item.get_closest_marker("scaling") and not selected:
            item.add_marker(skip)
