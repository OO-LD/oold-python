"""OO-LD schema and instance validation.

Answers two questions:

* is this a well-formed OO-LD schema, whose ``@context`` carries every property it declares
  into RDF without loss?
* does this instance document conform to the schema it names?

The same pipeline backs the library API, the ``oold validate`` CLI and the MCP server, so there
is one implementation to keep correct.

Requires the ``validation`` extra::

    pip install "oold[validation]"
"""

from __future__ import annotations

from .meta_store import (
    MetaBundle,
    MetaSchemaError,
    describe_store,
    fetch_remote,
    latest_version,
    resolve_selection,
    tracked_versions,
)
from .pipeline import (
    Options,
    run_compliance,
    validate_directory,
    validate_instance,
    validate_schema,
)
from .report import Check, Report, failure_reasons
from .resolve import Resolver, SchemaResolutionError

__all__ = [
    "Check",
    "MetaBundle",
    "MetaSchemaError",
    "Options",
    "Report",
    "Resolver",
    "SchemaResolutionError",
    "describe_store",
    "failure_reasons",
    "fetch_remote",
    "latest_version",
    "resolve_selection",
    "run_compliance",
    "tracked_versions",
    "validate_directory",
    "validate_instance",
    "validate_schema",
]
