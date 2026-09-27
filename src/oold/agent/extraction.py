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

import copy
import json
import re
from dataclasses import dataclass, field, replace
from typing import Any

from oold.agent.client import CallLog, ChatClient, TokenUsage, prompt_hash
from oold.agent.enforcement import (
    DecodeConstraint,
    Enforcement,
    Orchestration,
    OutputForm,
)
from oold.agent.prompts import (
    ExtractionRequest,
    build_messages,
    build_selection_messages,
    selection_schema,
)
from oold.agent.provider import Degradation, ProviderProfile, prepare, schema_hash
from oold.agent.union import union_schema

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
    selected: dict[str, tuple[str, ...]] = field(default_factory=dict)
    """The shortlist the select step produced, per entity.

    Recorded so a two-step failure can be attributed to a step. Without it,
    the true class never being offered and the fill step choosing wrongly from
    a shortlist that contained it look like the same failure."""
    prompt_sha256: str | None = None
    """Hash of the turns actually sent, folding included. Hashing the document
    instead would say two models got the same prompt when one of them had the
    system message folded into its user turn."""
    dropped: list[str] = field(default_factory=list)
    """Classes the commit-time gate removed, so the gate's effect is visible
    instead of being folded into a lower score."""
    invalid: list[str] = field(default_factory=list)
    """Why the answer still fails the schema, after any repair. Empty when it
    conforms and when the condition did not ask."""
    repairs: int = 0
    """How many times the answer was sent back with its errors."""

    @property
    def parsed(self) -> bool:
        return self.payload is not None

    def describe(self) -> dict[str, Any]:
        return {
            "parsed": self.parsed,
            "schema_sha256": self.schema_sha256,
            "prompt_sha256": self.prompt_sha256,
            "selected": {k: list(v) for k, v in self.selected.items()},
            "dropped": list(self.dropped),
            "invalid": list(self.invalid),
            "repairs": self.repairs,
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
        shortlist_k: int = 3,
    ) -> None:
        self.client = client
        self.enforcement = enforcement
        self.profile = profile
        self.orchestration = orchestration
        self.attempts = attempts
        self.shortlist_k = shortlist_k
        """How many classes the select step may keep per entity. One is the
        commit case, where a wrong selection cannot be recovered."""
        if orchestration in (Orchestration.RECURSIVE, Orchestration.SEGMENTED, Orchestration.MULTI_STEP):
            raise NotImplementedError(
                f"orchestration {orchestration.value} is not ported yet. It addresses "
                f"the entity graph, which comes after class selection works"
            )
        if shortlist_k < 1:
            raise ValueError("a shortlist of nothing leaves the second step no class to fill")

    def run(self, request: ExtractionRequest) -> ExtractionResult:
        if self.orchestration is Orchestration.SELECT_THEN_FILL:
            return self._select_then_fill(request)
        return self._single_shot(request)

    def _single_shot(self, request: ExtractionRequest) -> ExtractionResult:
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
        digest_prompt = prompt_hash(messages, fold_system=getattr(self.client, "fold_system", False))
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

        errors: list[str] = []
        repairs = 0
        if self.enforcement.validate_output and prepared is not None:
            payload, text, errors, repairs = self._validate_and_repair(
                payload, text, prepared, messages, response_format, log, digest
            )

        return ExtractionResult(
            text=text,
            payload=payload,
            calls=log,
            degradation=degradation,
            schema_sha256=digest,
            prompt_sha256=digest_prompt,
            dropped=dropped,
            invalid=errors,
            repairs=repairs,
        )

    def _validate_and_repair(
        self,
        payload: Any,
        text: str,
        schema: dict[str, Any],
        messages: list[Any],
        response_format: dict[str, Any] | None,
        log: CallLog,
        digest: str | None,
    ) -> tuple[Any, str, list[str], int]:
        """Check the answer against the schema, and offer it its errors back.

        The errors are handed over verbatim from the validator. Rewriting them
        into advice would make the repair rate a measure of how well the advice
        was worded, which is a different study.

        A repair that does not validate is kept anyway, with its errors
        recorded. Silently returning the last valid answer would report a
        conformance rate the arm did not achieve.
        """
        from oold.agent.repair import repair_message
        from oold.validation.instance_checks import validate_instance

        errors = [] if payload is None else validate_instance(payload, schema).errors
        repairs = 0
        while errors and repairs < self.enforcement.repair_attempts:
            repairs += 1
            turn = [*list(messages), repair_message(text, errors)]
            with log.timed("repair", self.client.model, attempt=repairs, schema_sha256=digest) as sink:
                reply = self.client.invoke(turn, response_format=response_format)
                sink.append(reply.usage or TokenUsage())
            text = reply.text
            candidate = reply.parsed if reply.parsed is not None else parse_json_answer(text)
            if candidate is None:
                break
            payload = candidate
            if self.enforcement.commit_gate:
                payload, _ = self._gate(payload)
            errors = validate_instance(payload, schema).errors
        return payload, text, errors, repairs

    def _select_then_fill(self, request: ExtractionRequest) -> ExtractionResult:
        """Shortlist the class, then fill the schema that shortlist implies.

        The fill step is sent the whole document again, not the mention the
        select step reported. A summary written by step one would be a
        bottleneck the grader cannot see past: an entity lost there would look
        like an extraction failure rather than a selection failure.
        """
        log = CallLog()
        selected, text = self._select(request, log)

        offered = tuple(dict.fromkeys(name for names in selected.values() for name in names))
        if not offered:
            return ExtractionResult(
                text=text,
                payload=None,
                calls=log,
                selected=selected,
            )

        # One fill call for every entity, so the classes are pooled across
        # them. With several entities that is weaker than a union per entity,
        # because entity A may be answered with entity B's class. The shortlist
        # dimension stays exact per entity, so the weakening is visible.
        narrowed = self.enforcement.with_catalogue(offered)
        filler = ExtractionAgent(self.client, narrowed, self.profile, attempts=self.attempts)
        result = filler._single_shot(request)
        for call in result.calls:
            log.append(replace(call, step="fill"))
        result.calls = log
        result.selected = selected
        return result

    def _select(self, request: ExtractionRequest, log: CallLog) -> tuple[dict[str, tuple[str, ...]], str]:
        """Ask which classes each entity could be, keeping at most k."""
        catalogue = self.enforcement.catalogue or ()
        if not catalogue:
            raise ValueError("select-then-fill needs a catalogue to select from")

        schema = selection_schema(catalogue, self.shortlist_k)
        prepared, _ = prepare(schema, self.profile, grounding=False)
        messages = build_selection_messages(request, self.enforcement, self.shortlist_k)
        response_format = prepared if self.enforcement.decode_constraint is not DecodeConstraint.NONE else None

        with log.timed("select", self.client.model, attempt=1, schema_sha256=schema_hash(prepared)) as sink:
            reply = self.client.invoke(messages, response_format=response_format)
            sink.append(reply.usage or TokenUsage())

        payload = reply.parsed if reply.parsed is not None else parse_json_answer(reply.text)
        allowed = set(catalogue)
        selected: dict[str, tuple[str, ...]] = {}
        for index, entity in enumerate(_entities_of(payload), start=1):
            if not isinstance(entity, dict):
                continue
            key = str(entity.get("id") or f"e{index}")
            names = [n for n in entity.get("candidates") or () if n in allowed]
            selected[key] = tuple(dict.fromkeys(names))[: self.shortlist_k]
        return selected, reply.text

    def _schema_for(self, request: ExtractionRequest) -> tuple[dict[str, Any] | None, Degradation | None, str | None]:
        """The schema this condition sends, and what preparing it cost."""
        needs_schema = (
            self.enforcement.schema_in_prompt or self.enforcement.decode_constraint is not DecodeConstraint.NONE
        )
        if request.schema is None or not needs_schema:
            return None, None, None

        # The union is built before the provider transform, not after. Building
        # it after would send an `anyOf` to a profile that rejects one, and the
        # degradation measure would report that nothing was lost because the
        # transform never saw it. An enum is pinned after, because pinning adds
        # values to a slot the transform has already shaped.
        source = request.schema
        if self.enforcement.decode_constraint is DecodeConstraint.JSON_SCHEMA_UNION:
            source = self._pin_union(copy.deepcopy(source), request.branches)

        prepared, degradation = prepare(source, self.profile, grounding=self.enforcement.grounding)
        if self.enforcement.decode_constraint is DecodeConstraint.JSON_SCHEMA_ENUM:
            prepared = self._pin_class(prepared)
            prepared = self._pin_units(prepared)
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

    def _pin_union(self, schema: dict[str, Any], branches: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
        """Replace the entity shape with a union over the offered classes.

        Fails loudly without branches, the same way :meth:`_pin_class` does.
        A union arm that quietly ran unconstrained would be reported as a
        finding about unions.
        """
        if not self.enforcement.catalogue:
            return schema
        if not branches:
            raise ValueError("a union constraint needs one branch per offered class, and the request carried none")
        offered = {name: branches[name] for name in self.enforcement.catalogue if name in branches}
        if not offered:
            raise ValueError("no offered class has a branch, so the union would admit nothing")
        target = _find_entity_items(schema)
        if target is None:
            raise ValueError("the schema has no entity shape to turn into a union")
        shared = {k: v for k, v in (target.get("properties") or {}).items() if k not in _CLASS_KEYS}
        union = union_schema(
            offered,
            shared={k: v for k, v in shared.items() if k not in _UNIT_KEYS},
            required=tuple(target.get("required") or ()),
        )
        target.clear()
        target.update(union)
        return schema

    def _pin_units(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Constrain the unit slot, when the corpus closes it.

        A quantity corpus enumerates the units each kind admits. Pinning the
        class and leaving the unit a free string enforces half of what the
        schema says, and the half left open is the one models get wrong.

        Silent when no unit enumeration was supplied, because a corpus that
        does not close the slot is a condition, not a mistake. That is the
        opposite of :meth:`_pin_class`, which raises: there the catalogue was
        asked for and the slot to put it in was missing.
        """
        if not self.enforcement.unit_catalogue:
            return schema
        target = _find_property(schema, _UNIT_KEYS)
        if target is None:
            raise ValueError("the schema has no unit property to pin, so the unit enumeration cannot be applied")
        target["enum"] = list(self.enforcement.unit_catalogue)
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

_UNIT_KEYS = ("unit", "units", "unit_symbol", "uom")


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


def _find_property(schema: Any, keys: tuple[str, ...]) -> dict[str, Any] | None:
    """The subschema for one of these property names, wherever it sits.

    Only names under a ``properties`` map count, so the ``type`` keyword of
    JSON Schema itself is never mistaken for a property called ``type``.
    """
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            for key in keys:
                target = properties.get(key)
                if isinstance(target, dict):
                    return target
        for value in schema.values():
            found = _find_property(value, keys)
            if found is not None:
                return found
    elif isinstance(schema, list):
        for item in schema:
            found = _find_property(item, keys)
            if found is not None:
                return found
    return None


def _entities_of(payload: Any) -> list[Any]:
    """The entity list in an answer, whatever the model called the wrapper."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for wrapper in ("entities", "instances", "items", "results"):
            value = payload.get(wrapper)
            if isinstance(value, list):
                return value
    return []


def _find_entity_items(schema: Any) -> dict[str, Any] | None:
    """The subschema describing one entity, which a union replaces.

    The object that carries the class slot. Replacing the array instead would
    make the union say the list is one of several kinds, not that each entry
    is.
    """
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict) and any(k in properties for k in _CLASS_KEYS):
            return schema
        for value in schema.values():
            found = _find_entity_items(value)
            if found is not None:
                return found
    elif isinstance(schema, list):
        for item in schema:
            found = _find_entity_items(item)
            if found is not None:
                return found
    return None


def _find_class_property(schema: Any) -> dict[str, Any] | None:
    """The subschema describing an entity's class, wherever it sits."""
    return _find_property(schema, _CLASS_KEYS)
