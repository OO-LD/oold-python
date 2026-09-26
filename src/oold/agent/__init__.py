"""Turn an OO-LD schema into a validated typed instance with an LLM.

Orchestration and enforcement are separate axes here, so a study can hold one
fixed while varying the other. The three agents in the `osl-eln-demo` project
become three values of :class:`Orchestration` rather than three code paths.

Nothing in the core of ``oold`` imports this package, so installing ``oold``
for typed data never pulls in an LLM client.

Requires the ``agent`` extra::

    uv add "oold[agent]"
    pip install "oold[agent]"
"""

from oold.agent.enforcement import (
    ARMS,
    DecodeConstraint,
    Enforcement,
    Orchestration,
    OutputForm,
    arm,
)
from oold.agent.provider import (
    PROFILES,
    Degradation,
    ProviderProfile,
    prepare,
    profile_for,
    schema_hash,
)

__all__ = [
    "ARMS",
    "PROFILES",
    "DecodeConstraint",
    "Degradation",
    "Enforcement",
    "Orchestration",
    "OutputForm",
    "ProviderProfile",
    "arm",
    "prepare",
    "profile_for",
    "schema_hash",
]
