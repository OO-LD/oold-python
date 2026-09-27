"""Running one extraction under one enforcement condition.

The agent is one skeleton with the enforcement supplied as data. Orchestration
is a separate axis, so a study can hold one fixed while varying the other,
which is the property the predecessor lacked: eight of ten differences between
its two arms were orchestration, so nothing it measured could be attributed to
typing.

What the agent returns is the model's answer and a record of how it was
obtained. Turning that answer into something scoreable belongs to whatever is
doing the scoring, so this package never learns what a benchmark is.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from oold.agent.client import CallLog, ChatClient, TokenUsage
from oold.agent.enforcement import (
    DecodeConstraint,
    Enforcement,
    Orchestration,
    OutputForm,
)
from oold.agent.prompts import ExtractionRequest, build_messages
from oold.agent.provider import Degradation, ProviderProfile, prepare, schema_hash

__all__ = ["ExtractionAgent", "ExtractionResult", "parse_json_answer"]

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


def parse_json_answer(text: str) -> Any | None:
    """Read JSON out of an answer, tolerating a markdown fence.

    Models wrap JSON in a fence even when told not to, and refusing those
    would measure instruction-following dressed up as a parse rate. Anything
    beyond stripping a fence is left alone, because repairing malformed JSON
    would hide a real failure of the decode-time constraint.
    """
    if not text or not text.strip():
        return None
    candidate = _FENCE.sub("", text).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


@dataclass
class ExtractionResult:
    """One answer, and everything needed to say how it was produced."""

    text: str
    payload: Any | None
    calls: CallLog
    degradation: Degradation | None = None
    schema_sha256: str | None = None
    dropped: list[str] = field(default_factory=list)
    """Classes the commit-time gate removed, so the gate's effect is visible
    instead of being folded into a lower score."""

    @property
    def parsed(self) -> bool:
        return self.payload is not None

    def describe(self) -> dict[str, Any]:
        return {
            "parsed": self.parsed,
            "schema_sha256": self.schema_sha256,
            "dropped": list(self.dropped),
            "degradation": self.degradation.describe() if self.degradation else None,
            "calls": self.calls.describe(),
        }


class ExtractionAgent:
    """Turn a document into a model's answer under one condition."""

    def __init__(
        self,
        client: ChatClient,
        enforcement: Enforcement,
        profile: ProviderProfile,
        orchestration: Orchestration = Orchestration.SINGLE_SHOT,
        *,
        attempts: int = 1,
    ) -> None:
        self.client = client
        self.enforcement = enforcement
        self.profile = profile
        self.orchestration = orchestration
        self.attempts = attempts
        if orchestration is not Orchestration.SINGLE_SHOT:
            raise NotImplementedError(
                f"orchestration {orchestration.value} is not ported yet. "
                f"Only {Orchestration.SINGLE_SHOT.value} runs today"
            )

    def run(self, request: ExtractionRequest) -> ExtractionResult:
        log = CallLog()
        prepared, degradation, digest = self._schema_for(request)
        messages = build_messages(
            ExtractionRequest(
                document=request.document,
                schema=prepared if self.enforcement.schema_in_prompt else None,
                instruction=request.instruction,
            ),
            self.enforcement,
        )
        response_format = (
            prepared
            if prepared is not None and self.enforcement.decode_constraint is not DecodeConstraint.NONE
            else None
        )

        text = ""
        payload: Any | None = None
        for attempt in range(1, self.attempts + 1):
            with log.timed("extract", self.client.model, attempt=attempt, schema_sha256=digest) as sink:
                reply = self.client.invoke(messages, response_format=response_format)
                sink.append(reply.usage or TokenUsage())
            text = reply.text
            payload = reply.parsed if reply.parsed is not None else parse_json_answer(text)
            if payload is not None or self.enforcement.output_form is OutputForm.PROSE:
                break

        dropped: list[str] = []
        if self.enforcement.commit_gate and payload is not None:
            payload, dropped = self._gate(payload)

        return ExtractionResult(
            text=text,
            payload=payload,
            calls=log,
            degradation=degradation,
            schema_sha256=digest,
            dropped=dropped,
        )

    def _schema_for(self, request: ExtractionRequest) -> tuple[dict[str, Any] | None, Degradation | None, str | None]:
        """The schema this condition sends, and what preparing it cost."""
        needs_schema = (
            self.enforcement.schema_in_prompt or self.enforcement.decode_constraint is not DecodeConstraint.NONE
        )
        if request.schema is None or not needs_schema:
            return None, None, None
        prepared, degradation = prepare(request.schema, self.profile, grounding=self.enforcement.grounding)
        if self.enforcement.decode_constraint is DecodeConstraint.JSON_SCHEMA_ENUM:
            prepared = self._pin_class(prepared)
        return prepared, degradation, schema_hash(prepared)

    def _pin_class(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Constrain the class slot to the catalogue at decode time.

        Fails loudly when there is no slot to constrain. A silent no-op here
        would make an arm that was meant to be constrained run unconstrained,
        and the result would look like a finding about constraints.
        """
        if not self.enforcement.catalogue:
            return schema
        target = _find_class_property(schema)
        if target is None:
            raise ValueError("the schema has no class property to pin, so the decode-time constraint cannot be applied")
        target["enum"] = list(self.enforcement.catalogue)
        return schema

    def _gate(self, payload: Any) -> tuple[Any, list[str]]:
        """Drop entities whose class is not in the catalogue.

        The filtered result is returned and used. Keeping the corrections and
        discarding the removals is the bug that inflated the predecessor's
        missing-entity count for months.
        """
        allowed = set(self.enforcement.catalogue or ())
        if not allowed:
            return payload, []
        dropped: list[str] = []

        def keep(entity: Any) -> bool:
            if not isinstance(entity, dict):
                return True
            name = _class_of(entity)
            if name is None or name in allowed:
                return True
            suffixed = [a for a in allowed if a.endswith("." + name)]
            if len(suffixed) == 1:
                _set_class(entity, suffixed[0])
                return True
            dropped.append(name)
            return False

        if isinstance(payload, list):
            return [e for e in payload if keep(e)], dropped
        if isinstance(payload, dict):
            for wrapper in ("entities", "instances", "items", "results"):
                if isinstance(payload.get(wrapper), list):
                    payload[wrapper] = [e for e in payload[wrapper] if keep(e)]
                    return payload, dropped
            return (payload if keep(payload) else None), dropped
        return payload, dropped


_CLASS_KEYS = ("type", "@type", "class", "class_path", "schema_path", "kind")


def _class_of(entity: dict[str, Any]) -> str | None:
    for key in _CLASS_KEYS:
        value = entity.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list) and value and isinstance(value[0], str):
            return value[0].strip()
    return None


def _set_class(entity: dict[str, Any], name: str) -> None:
    for key in _CLASS_KEYS:
        if key in entity:
            entity[key] = [name] if isinstance(entity[key], list) else name
            return


def _find_class_property(schema: Any) -> dict[str, Any] | None:
    """The subschema describing an entity's class, wherever it sits."""
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            for key in _CLASS_KEYS:
                target = properties.get(key)
                if isinstance(target, dict):
                    return target
        for value in schema.values():
            found = _find_class_property(value)
            if found is not None:
                return found
    elif isinstance(schema, list):
        for item in schema:
            found = _find_class_property(item)
            if found is not None:
                return found
    return None
