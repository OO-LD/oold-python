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

from oold.agent.client import (
    Call,
    CallLog,
    ChatClient,
    ChatResponse,
    Message,
    TokenUsage,
)
from oold.agent.enforcement import (
    ARMS,
    DecodeConstraint,
    Enforcement,
    Orchestration,
    OutputForm,
    arm,
)
from oold.agent.extraction import (
    ExtractionAgent,
    ExtractionResult,
    parse_json_answer,
)
from oold.agent.prompts import ExtractionRequest, build_messages
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
    "Call",
    "CallLog",
    "ChatClient",
    "ChatResponse",
    "DecodeConstraint",
    "Degradation",
    "Enforcement",
    "ExtractionAgent",
    "ExtractionRequest",
    "ExtractionResult",
    "Message",
    "Orchestration",
    "OutputForm",
    "ProviderProfile",
    "TokenUsage",
    "arm",
    "build_messages",
    "parse_json_answer",
    "prepare",
    "profile_for",
    "schema_hash",
]
