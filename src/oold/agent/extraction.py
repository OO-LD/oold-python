"""Running one extraction under one enforcement condition.

The agent is one skeleton with the enforcement supplied as data. Orchestration
is a separate axis, so a study can hold one fixed while varying the other,
the property the predecessor lacked: eight of ten differences between
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
    build_property_messages,
    build_selection_messages,
    property_schema,
    selection_schema,
)
from oold.agent.provider import Degradation, ProviderProfile, prepare, schema_hash
from oold.agent.union import hierarchy_union, union_schema

__all__ = ["Edge", "ExtractionAgent", "ExtractionResult", "PlannedEntity", "parse_json_answer"]

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


@dataclass(frozen=True)
class PlannedEntity:
    """One entity the plan step found, as the fill step is told about it."""

    key: str
    """The id both steps use for this entity.

    Invented by the model in the plan step and offered back to it in the fill
    step. An id attached afterwards by position never puts the question of
    whether two mentions are one entity to the model at all, which is why the
    predecessor could not ask it."""
    classes: tuple[str, ...]
    """The shortlist, most likely first. Empty when the plan placed the entity
    in no class, which leaves it out of the fill step."""
    mention: str = ""
    """The words the plan read it from, used to name it in the fill prompt."""


@dataclass(frozen=True)
class Edge:
    """One link an answer asserted, by the ids the plan handed out."""

    source: str
    prop: str
    target: str

    def describe(self) -> dict[str, str]:
        return {"source": self.source, "prop": self.prop, "target": self.target}


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
    links: list[Edge] = field(default_factory=list)
    """Every edge the answer asserted between planned entities. Empty for an
    orchestration that hands out no ids, where a link has nothing to name."""
    dangling: list[Edge] = field(default_factory=list)
    """The links whose target was never emitted.

    A subset of :attr:`links` and not a removal. The edge stays in the payload,
    because an answer pointing at an entity it failed to report is a different
    failure from an answer reporting no edge, and dropping it would make the
    two the same number."""
    unpinned: list[str] = field(default_factory=list)
    """Reference properties left open because no planned entity fits their
    range. Those slots ran unconstrained, and the record says which."""
    properties_chosen: dict[str, tuple[str, ...]] = field(default_factory=dict)
    """The properties the property step kept, per entity.

    Recorded for the reason :attr:`selected` is. An orchestration that closes
    the property slot can fail by never offering the property the document
    states, or by offering it and the extract step leaving it empty, and
    without this the two are the same missing value."""

    @property
    def parsed(self) -> bool:
        return self.payload is not None

    def describe(self) -> dict[str, Any]:
        return {
            "parsed": self.parsed,
            "schema_sha256": self.schema_sha256,
            "prompt_sha256": self.prompt_sha256,
            "selected": {k: list(v) for k, v in self.selected.items()},
            "properties_chosen": {k: list(v) for k, v in self.properties_chosen.items()},
            "dropped": list(self.dropped),
            "invalid": list(self.invalid),
            "repairs": self.repairs,
            "links": [edge.describe() for edge in self.links],
            "dangling": [edge.describe() for edge in self.dangling],
            "unpinned": list(self.unpinned),
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
        close_properties: bool = True,
        plan_retry: bool | None = None,
    ) -> None:
        self.client = client
        self.enforcement = enforcement
        self.profile = profile
        self.orchestration = orchestration
        self.attempts = attempts
        self._mentions: dict[str, str] = {}
        """What the select step read each entity from, used only to say which
        entity a fill call is for when a document holds several."""
        self.shortlist_k = shortlist_k
        """How many classes the select step may keep per entity. One is the
        commit case, where a wrong selection cannot be recovered."""
        self.close_properties = close_properties
        """Whether the property step's answer removes the slots it left out.

        On, the extract schema carries the chosen properties and the required
        ones and nothing else, which is the direct analogue of closing the
        class slot. Off, the chosen properties are named in the extract prompt
        and the schema stays whole, so a property the step missed can still be
        answered. The two are different claims about what closing a slot buys,
        so which one ran is declared rather than assumed."""
        self.plan_retry = (orchestration is Orchestration.MULTI_STEP) if plan_retry is None else plan_retry
        """Whether a first call that answered with the schema is asked again.

        Defaulted from the orchestration rather than fixed, so the mitigation
        can be run on the orchestration it was not written for. Without that,
        a multi-step arm beating a segmented one on a model that echoes
        schemas would be reporting the retry as a property of the pipeline."""
        if orchestration is Orchestration.RECURSIVE:
            raise NotImplementedError(
                "orchestration recursive is not ported yet. It addresses "
                "the entity graph, which comes after class selection works"
            )
        if shortlist_k < 1:
            raise ValueError("a shortlist of nothing leaves the second step no class to fill")

    def run(self, request: ExtractionRequest) -> ExtractionResult:
        if self.orchestration is Orchestration.MULTI_STEP:
            return self._multi_step(request)
        if self.orchestration is Orchestration.SEGMENTED:
            return self._segmented(request)
        if self.orchestration is Orchestration.SELECT_THEN_FILL:
            return self._select_then_fill(request)
        return self._single_shot(request)

    def _single_shot(
        self,
        request: ExtractionRequest,
        *,
        plan: tuple[PlannedEntity, ...] = (),
        filling: tuple[str, ...] = (),
    ) -> ExtractionResult:
        log = CallLog()
        prepared, degradation, digest, unpinned = self._schema_for(request, plan, filling)
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
            unpinned=unpinned,
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
        self._mentions: dict[str, str] = {}
        selected, text = self._select(request, log)

        offered = tuple(dict.fromkeys(name for names in selected.values() for name in names))
        if not offered:
            return ExtractionResult(
                text=text,
                payload=None,
                calls=log,
                selected=selected,
            )

        # One call per distinct shortlist, not one per document. Pooling every
        # entity's candidates into one constraint lets entity A be answered
        # with entity B's class, which is the thing the shortlist was for.
        # Entities that shortlisted the same classes share a call, so a
        # single-entity document still costs one.
        groups: dict[tuple[str, ...], list[str]] = {}
        for key, names in selected.items():
            if names:
                groups.setdefault(tuple(names), []).append(key)

        merged: list[Any] = []
        last: ExtractionResult | None = None
        for classes, keys in groups.items():
            narrowed = self.enforcement.with_catalogue(classes)
            filler = ExtractionAgent(self.client, narrowed, self.profile, attempts=self.attempts)
            step = ExtractionRequest(
                document=request.document,
                schema=request.schema,
                branches=request.branches,
                parents=request.parents,
                instruction=self._fill_instruction(request, selected, keys) if len(groups) > 1 else None,
            )
            outcome = filler._single_shot(step)
            for call in outcome.calls:
                log.append(replace(call, step="fill"))
            merged.extend(_entities_of(outcome.payload))
            last = outcome

        if last is None:
            return ExtractionResult(text=text, payload=None, calls=log, selected=selected)
        last.payload = {"entities": merged} if merged else None
        last.calls = log
        last.selected = selected
        return last

    def _fill_instruction(
        self,
        request: ExtractionRequest,
        selected: dict[str, tuple[str, ...]],
        keys: list[str],
    ) -> str:
        """Which entities this call is for, when a document holds several.

        Named by the words the select step read them from, because an
        identifier it invented means nothing to a model reading the document
        again. Omitted entirely when there is one group, so the single-entity
        case sends the same prompt the single-shot arm does.
        """
        mentions = [self._mentions.get(key) or key for key in keys]
        listed = ", ".join(f'"{mention}"' for mention in mentions)
        return (
            f"Read the document and report only the entities identified as {listed}, with the values stated for each."
        )

    def _segmented(self, request: ExtractionRequest) -> ExtractionResult:
        """Plan the whole document, then fill the plan.

        The plan is the unit of work, which is the difference from
        select-then-fill. Grouping by shortlist is enough while every answer is
        one entity's own values, and an edge is nobody's own value: the call
        holding a link has to know that the entity at the other end exists and
        what it is called, even when another call is filling it.

        The document is sent again in full, for the reason it is under
        select-then-fill: a summary written by step one would be a bottleneck
        the grader cannot see past, and an entity lost there would read as an
        extraction failure. What step two gains over that arm is the ids, so a
        link has a name to point at.
        """
        log = CallLog()
        self._mentions = {}
        selected, text = self._select(request, log, step="plan", insist=self.plan_retry)
        plan = tuple(
            PlannedEntity(key=key, classes=classes, mention=self._mentions.get(key, ""))
            for key, classes in selected.items()
        )

        # One call per distinct shortlist, as select-then-fill does, and for the
        # same reason: pooling the candidates lets one entity be answered with
        # another's class.
        groups: dict[tuple[str, ...], list[str]] = {}
        for entity in plan:
            if entity.classes:
                groups.setdefault(entity.classes, []).append(entity.key)
        if not groups:
            return ExtractionResult(text=text, payload=None, calls=log, selected=selected)

        merged: list[Any] = []
        unpinned: list[str] = []
        last: ExtractionResult | None = None
        for classes, keys in groups.items():
            narrowed = self.enforcement.with_catalogue(classes)
            filler = ExtractionAgent(self.client, narrowed, self.profile, attempts=self.attempts)
            step = ExtractionRequest(
                document=request.document,
                schema=request.schema,
                branches=request.branches,
                parents=request.parents,
                ranges=request.ranges,
                instruction=self._plan_instruction(request, plan, keys),
            )
            outcome = filler._single_shot(step, plan=plan, filling=tuple(keys))
            for call in outcome.calls:
                log.append(replace(call, step="fill"))
            merged.extend(_entities_of(outcome.payload))
            unpinned.extend(name for name in outcome.unpinned if name not in unpinned)
            last = outcome

        if last is None:
            return ExtractionResult(text=text, payload=None, calls=log, selected=selected)
        links, dangling = _edges_of(merged, request.ranges)
        last.payload = {"entities": merged} if merged else None
        last.calls = log
        last.selected = selected
        last.links = links
        last.dangling = dangling
        last.unpinned = unpinned
        return last

    def _plan_instruction(
        self,
        request: ExtractionRequest,
        plan: tuple[PlannedEntity, ...],
        keys: list[str],
    ) -> str:
        """Which planned entities this call reports, and under which ids.

        The ids are stated even when one call covers the whole plan, which is
        where this parts company with :meth:`_fill_instruction`. There an id is
        an internal label and naming it would only add words. Here it is the
        answer's own key and the thing a link points at.

        Entities another call is filling are named too, as targets and not as
        work. Without them, a document whose source and target shortlisted
        different classes could never state the edge between them, because the
        call holding the source would not know the target had a name.
        """
        wanted = set(keys)
        listed = "; ".join(_named(entity) for entity in plan if entity.key in wanted)
        sections = [
            f"Read the document and report these entities, each under the id given here: {listed}.",
            "Give that id as the value of the id property.",
        ]
        others = [entity for entity in plan if entity.key not in wanted]
        if others:
            sections.append("The document also describes " + "; ".join(_named(entity) for entity in others) + ".")
        if request.ranges:
            sections.append(
                "Where a property of an entity points at another of these entities, give that entity's id as the value."
            )
        return " ".join(sections)

    def _multi_step(self, request: ExtractionRequest) -> ExtractionResult:
        """Detect, choose properties per entity, extract, link.

        Segmented with one call inserted between the plan and the fill. The
        plan says which classes an entity may be, the property step says which
        of those classes' slots the document fills at all, and the extract step
        answers what is left against ids both ends agree on.

        Four steps and not the predecessor's five. Its construct step sent the
        hints and the schema and no document, so it asked a model to reformat
        values it had already produced against a schema it had already matched;
        :meth:`_validate_and_repair` covers that failure and hands the
        validator's reasons back verbatim. Its deduplication step asks whether
        two entities are one, which is a question about identity across
        documents with a corpus of its own, and a judge sitting inside an
        orchestration cannot be scored apart from the extraction around it.

        Whether the property step binds is :attr:`close_properties` and not a
        fact about this pipeline. An entity the step leaves with nothing is
        extracted with its class and its id alone, because that is what the
        step said, and restoring the slots behind its back would hide a
        step-two failure inside step three.
        """
        log = CallLog()
        self._mentions = {}
        selected, text = self._select(request, log, step="detect", insist=self.plan_retry)
        plan = tuple(
            PlannedEntity(key=key, classes=classes, mention=self._mentions.get(key, ""))
            for key, classes in selected.items()
        )
        placed = tuple(entity for entity in plan if entity.classes)
        if not placed:
            return ExtractionResult(text=text, payload=None, calls=log, selected=selected)

        chosen = self._choose_properties(request, log, placed, self._available_properties(request, placed))
        required = _required_properties(request.schema)

        # Grouped by shortlist and by chosen properties together, where
        # segmented groups by shortlist alone. The extra key is the same
        # argument one step on: entities sharing a call share the schema that
        # call is sent, so two that chose different properties can no more
        # share one than two that shortlisted different classes.
        groups: dict[tuple[tuple[str, ...], tuple[str, ...]], list[str]] = {}
        for entity in placed:
            groups.setdefault((entity.classes, chosen.get(entity.key, ())), []).append(entity.key)

        merged: list[Any] = []
        unpinned: list[str] = []
        last: ExtractionResult | None = None
        for (classes, kept), keys in groups.items():
            narrowed = self.enforcement.with_catalogue(classes)
            filler = ExtractionAgent(self.client, narrowed, self.profile, attempts=self.attempts)
            keep = set(kept) | required
            step = ExtractionRequest(
                document=request.document,
                schema=_trim_properties(request.schema, keep) if self.close_properties else request.schema,
                branches=_trim_branches(request.branches, keep) if self.close_properties else request.branches,
                parents=request.parents,
                ranges=request.ranges,
                instruction=self._extract_instruction(request, plan, keys, kept),
            )
            outcome = filler._single_shot(step, plan=plan, filling=tuple(keys))
            for call in outcome.calls:
                log.append(replace(call, step="extract"))
            merged.extend(_entities_of(outcome.payload))
            unpinned.extend(name for name in outcome.unpinned if name not in unpinned)
            last = outcome

        if last is None:
            return ExtractionResult(text=text, payload=None, calls=log, selected=selected)
        links, dangling = _edges_of(merged, request.ranges)
        last.payload = {"entities": merged} if merged else None
        last.calls = log
        last.selected = selected
        last.properties_chosen = chosen
        last.links = links
        last.dangling = dangling
        last.unpinned = unpinned
        return last

    def _available_properties(
        self,
        request: ExtractionRequest,
        plan: tuple[PlannedEntity, ...],
    ) -> dict[str, tuple[str, ...]]:
        """What each planned entity may carry, before the document is read.

        The union over the entity's shortlist, for the reason
        :func:`_compatible_ids` takes the union: the extract step has not
        committed to one class yet, and offering only the first class's
        properties would rule out a value the second call may well state.

        Intersected with the answer shape and in its order, so the step can
        only name a slot the extract call actually has. A corpus that declares
        no branches falls back to the whole shape, which asks the same question
        over every property the schema offers.
        """
        offered = _shape_properties(request.schema)
        if not offered:
            return {}
        lineage = {name: tuple(values) for name, values in (request.parents or {}).items()}
        available: dict[str, tuple[str, ...]] = {}
        for entity in plan:
            admitted = _admitted_properties(entity.classes, request.branches, lineage)
            names = tuple(name for name in offered if not admitted or name in admitted)
            if names:
                available[entity.key] = names
        return available

    def _choose_properties(
        self,
        request: ExtractionRequest,
        log: CallLog,
        plan: tuple[PlannedEntity, ...],
        available: dict[str, tuple[str, ...]],
    ) -> dict[str, tuple[str, ...]]:
        """Ask which of each entity's own properties the document fills.

        One call for the whole plan, with one enumeration per entity. The
        predecessor asked per entity in its construct step, which costs a call
        per entity for an answer one schema can carry.

        A name the entity cannot carry is dropped rather than repaired, the way
        :meth:`_select` drops a candidate outside the catalogue. The
        enumeration already said what was legal, and keeping the name would put
        a slot in the extract schema that no class on the shortlist declares.
        """
        if not available:
            return {}
        schema = property_schema(available)
        prepared, _ = prepare(schema, self.profile, grounding=False)
        named = {entity.key: f"{_named(entity)}, {'/'.join(entity.classes)}" for entity in plan}
        messages = build_property_messages(request, available, named)
        response_format = prepared if self.enforcement.decode_constraint is not DecodeConstraint.NONE else None

        with log.timed("properties", self.client.model, attempt=1, schema_sha256=schema_hash(prepared)) as sink:
            reply = self.client.invoke(messages, response_format=response_format)
            sink.append(reply.usage or TokenUsage())

        answered = _fillable_of(reply.parsed if reply.parsed is not None else parse_json_answer(reply.text), available)
        return {
            key: tuple(name for name in names if name in set(answered.get(key) or ()))
            for key, names in available.items()
        }

    def _extract_instruction(
        self,
        request: ExtractionRequest,
        plan: tuple[PlannedEntity, ...],
        keys: list[str],
        kept: tuple[str, ...],
    ) -> str:
        """What :meth:`_plan_instruction` says, and which properties to fill.

        The properties are named even when the schema already carries only
        them, as the ids are named even when the id slot is already enumerated.
        An arm that shows no schema, and an arm whose schema a provider
        flattened, both still have to be told.
        """
        base = self._plan_instruction(request, plan, keys)
        if kept:
            return f"{base} Report only these properties for them: {', '.join(kept)}."
        return f"{base} The document gives no property value for them, so report the class and the id only."

    def _select(
        self,
        request: ExtractionRequest,
        log: CallLog,
        *,
        step: str = "select",
        insist: bool = False,
    ) -> tuple[dict[str, tuple[str, ...]], str]:
        """Ask which classes each entity could be, keeping at most k.

        ``step`` names the call in the log. Two orchestrations ask this same
        question and spend different amounts on what follows, so their first
        calls are attributed apart rather than pooled under one name.
        """
        catalogue = self.enforcement.catalogue or ()
        if not catalogue:
            raise ValueError(f"{self.orchestration.value} needs a catalogue to select from")

        schema = selection_schema(catalogue, self.shortlist_k)
        prepared, _ = prepare(schema, self.profile, grounding=False)
        messages = build_selection_messages(request, self.enforcement, self.shortlist_k)
        response_format = prepared if self.enforcement.decode_constraint is not DecodeConstraint.NONE else None

        with log.timed(step, self.client.model, attempt=1, schema_sha256=schema_hash(prepared)) as sink:
            reply = self.client.invoke(messages, response_format=response_format)
            sink.append(reply.usage or TokenUsage())

        payload = reply.parsed if reply.parsed is not None else parse_json_answer(reply.text)
        text = reply.text
        if insist:
            payload, text = self._insist(
                payload,
                text,
                schema,
                messages,
                response_format,
                log,
                step=step,
                digest=schema_hash(prepared),
            )
        allowed = set(catalogue)
        selected: dict[str, tuple[str, ...]] = {}
        for index, entity in enumerate(_entities_of(payload), start=1):
            if not isinstance(entity, dict):
                continue
            key = str(entity.get("id") or f"e{index}")
            names = [n for n in entity.get("candidates") or () if n in allowed]
            selected[key] = tuple(dict.fromkeys(names))[: self.shortlist_k]
            mention = entity.get("mention")
            if isinstance(mention, str) and mention.strip():
                self._mentions[key] = mention.strip()
        return selected, text

    def _insist(
        self,
        payload: Any,
        text: str,
        schema: dict[str, Any],
        messages: list[Any],
        response_format: dict[str, Any] | None,
        log: CallLog,
        *,
        step: str,
        digest: str | None,
    ) -> tuple[Any, str]:
        """Ask once more when the first answer was not an answer.

        gpt-5-nano returns the selection schema itself instead of an instance
        of it on about a third of plan calls, and on none at all when the first
        call asks for values: a single-shot arm has no call whose answer is a
        structure, so there is nothing to echo. Any orchestration whose first
        call asks for a structure inherits that, and it costs the whole cell,
        because the classes the plan did not choose are the classes the later
        steps may not answer with.

        The trigger is both conditions at once: the answer names no entity and
        it fails the schema it was asked for. An answer that names entities
        under a wrapper the schema does not declare is usable and is left
        alone, and an answer that validates and names none is a document with
        nothing in it rather than a failed call.

        The validator's reasons go back verbatim, as they do for an invalid
        extraction, so the retry rate stays a measure of the model and not of
        how the advice was worded.
        """
        from oold.agent.repair import repair_message
        from oold.validation.instance_checks import validate_instance

        if _entities_of(payload):
            return payload, text
        errors = validate_instance(payload, schema).errors
        if not errors:
            return payload, text

        turn = [*list(messages), repair_message(text, errors)]
        with log.timed(step, self.client.model, attempt=2, schema_sha256=digest) as sink:
            reply = self.client.invoke(turn, response_format=response_format)
            sink.append(reply.usage or TokenUsage())
        retried = reply.parsed if reply.parsed is not None else parse_json_answer(reply.text)
        if retried is None:
            return payload, text
        return retried, reply.text

    def _schema_for(
        self,
        request: ExtractionRequest,
        plan: tuple[PlannedEntity, ...] = (),
        filling: tuple[str, ...] = (),
    ) -> tuple[dict[str, Any] | None, Degradation | None, str | None, list[str]]:
        """The schema this condition sends, and what preparing it cost."""
        needs_schema = (
            self.enforcement.schema_in_prompt or self.enforcement.decode_constraint is not DecodeConstraint.NONE
        )
        if request.schema is None or not needs_schema:
            return None, None, None, []

        # The union is built before the provider transform, not after. Building
        # it after would send an `anyOf` to a profile that rejects one, and the
        # degradation measure would report that nothing was lost because the
        # transform never saw it. An enum is pinned after, because pinning adds
        # values to a slot the transform has already shaped.
        source = request.schema
        if self.enforcement.decode_constraint is DecodeConstraint.JSON_SCHEMA_UNION:
            source = self._pin_union(copy.deepcopy(source), request.branches, request.parents)

        prepared, degradation = prepare(source, self.profile, grounding=self.enforcement.grounding)
        if self.enforcement.decode_constraint is DecodeConstraint.JSON_SCHEMA_ENUM:
            prepared = self._pin_class(prepared)
            prepared = self._pin_units(prepared)

        unpinned: list[str] = []
        if plan:
            # The id slot goes in whatever the decode constraint is, because it
            # belongs to the orchestration and not to the enforcement: an answer
            # stating no id cannot be joined back to the plan, and an arm that
            # only shows its schema still has to ask for one. The reference
            # enums go in where the decoder is engaged and nowhere else, so the
            # decode axis keeps meaning what it means everywhere else.
            prepared = self._pin_identity(prepared, filling)
            if self.enforcement.decode_constraint is not DecodeConstraint.NONE:
                prepared, unpinned = self._pin_references(prepared, plan, request.ranges, request.parents)
        return prepared, degradation, schema_hash(prepared), unpinned

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

    def _pin_union(
        self,
        schema: dict[str, Any],
        branches: dict[str, dict[str, Any]] | None,
        parents: dict[str, tuple[str, ...]] | None = None,
    ) -> dict[str, Any]:
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
        # Shared means what no branch defines. Copying every property into
        # every branch is harmless where a class narrows one slot out of three
        # and ruinous where it decides which of five hundred exist: the same
        # union came to 1.5 MB on a corpus whose flat schema is 60 kB.
        narrowed = {name for branch in offered.values() for name in branch}
        shared = {
            name: definition
            for name, definition in (target.get("properties") or {}).items()
            if name not in _CLASS_KEYS and name not in narrowed
        }
        if parents:
            # The offered classes and what they inherit from, and nothing else.
            # A catalogue carries a branch for every class it knows, so sending
            # all of them would ship the ancestry of a hundred classes to
            # constrain twenty-five. The choice stays the offered classes: an
            # ancestor carried only to hold shared properties is not an answer.
            lineage = {name: tuple(values) for name, values in parents.items()}
            needed = set(offered)
            queue = list(needed)
            while queue:
                current = queue.pop()
                for ancestor in lineage.get(current, ()):
                    if ancestor in branches and ancestor not in needed:
                        needed.add(ancestor)
                        queue.append(ancestor)
            union = hierarchy_union(
                {name: branches[name] for name in branches if name in needed},
                {name: values for name, values in lineage.items() if name in needed},
                concrete=tuple(offered),
            )
            if shared:
                union.setdefault("properties", {}).update(shared)
        else:
            union = union_schema(
                offered,
                shared=shared,
                required=tuple(name for name in (target.get("required") or ()) if name not in narrowed),
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

    def _pin_identity(self, schema: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
        """Give the answer a slot for the id the plan assigned.

        Pinned to the ids this call is for, so one call cannot answer with an
        entity another call is responsible for and have it counted twice. An id
        the model states, rather than one attached afterwards by position, is
        also the only form in which the question of whether two mentions are
        one entity is ever put to the model.

        Fails loudly when there is no entity shape to carry it, the way
        :meth:`_pin_class` does. A plan that cannot be joined to the answer
        would report every edge as dangling and read as a finding about links.
        """
        shapes = _entity_shapes(schema)
        if not shapes:
            raise ValueError("the schema has no entity shape to carry an id, so the plan cannot reach the answer")
        for shape in shapes:
            properties = shape.setdefault("properties", {})
            name = next((key for key in _ID_KEYS if key in properties), _ID_KEYS[0])
            slot = dict(properties.get(name) or {})
            slot["type"] = "string"
            slot.setdefault("description", "The id this entity was planned under.")
            if keys:
                slot["enum"] = list(keys)
            properties[name] = slot
            required = shape.setdefault("required", [])
            if name not in required:
                required.append(name)
        return schema

    def _pin_references(
        self,
        schema: dict[str, Any],
        plan: tuple[PlannedEntity, ...],
        ranges: dict[str, tuple[str, ...]] | None,
        parents: dict[str, tuple[str, ...]] | None = None,
    ) -> tuple[dict[str, Any], list[str]]:
        """Constrain each reference slot to the entities that could fill it.

        A link left as a free string admits a target that is not on the page,
        which costs an invented entity on top of the wrong edge. The candidates
        are the planned entities whose shortlist holds the property's range or
        a class descended from it, so an edge can only reach something the plan
        found.

        A property whose range no planned entity fits is left as the schema
        declares it and named in the return. An empty ``enum`` is not a tighter
        constraint but an unsatisfiable one: the strict subsets reject it
        outright, and one that accepted it would leave a required slot with no
        legal value, so a document whose target went undetected would fail on
        the schema instead of on the edge. Left open, the failure stays where it
        happened, and the name makes it countable.

        A property the prepared schema does not carry is passed over. The
        answer surface can lose one legitimately, by a catalogue trim upstream
        or by a provider's optional-property limit, and a slot that is not
        offered is not a slot left open.
        """
        if not ranges:
            return schema, []
        shapes = _entity_shapes(schema)
        if not shapes:
            raise ValueError("the schema has no entity shape to pin a reference in")

        lineage = {name: tuple(values) for name, values in (parents or {}).items()}
        unpinned: list[str] = []
        for name, admitted in ranges.items():
            carrying = [shape for shape in shapes if name in (shape.get("properties") or {})]
            if not carrying:
                continue
            targets = _compatible_ids(plan, admitted, lineage)
            if not targets:
                unpinned.append(name)
                continue
            for shape in carrying:
                properties = shape["properties"]
                declared = properties[name]
                # Null is how a model declines a property under a subset that
                # makes every property required. A pinned slot that dropped it
                # would force an edge out of every entity that has the slot.
                values: list[Any] = list(targets)
                if _accepts_null(declared):
                    values.append(None)
                    kind: Any = ["string", "null"]
                else:
                    kind = "string"
                described = declared.get("description") if isinstance(declared, dict) else None
                properties[name] = {
                    "type": kind,
                    "enum": values,
                    "description": described or f"The id of the entity {name} points at.",
                }
        return schema, unpinned

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

_ID_KEYS = ("id", "@id", "entity_id", "key")


def _named(entity: PlannedEntity) -> str:
    """One planned entity as the fill prompt names it."""
    return f'{entity.key} ("{entity.mention}")' if entity.mention else entity.key


def _is_entity_shape(node: Any) -> bool:
    """Whether this object describes one entity rather than the answer."""
    if not isinstance(node, dict):
        return False
    properties = node.get("properties")
    return isinstance(properties, dict) and any(key in properties for key in _CLASS_KEYS)


def _entity_shapes(schema: Any) -> list[dict[str, Any]]:
    """Every object an entity may take, one per union branch.

    A union is recognised before the objects inside it, so pinning reaches all
    of its branches. Pinning the first branch alone would constrain one class
    and leave the others open, which reads as a finding about that class.
    """
    found: list[dict[str, Any]] = []

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if not isinstance(node, dict):
            return
        for combinator in ("anyOf", "oneOf"):
            branches = node.get(combinator)
            if isinstance(branches, list) and any(_is_entity_shape(branch) for branch in branches):
                found.extend(branch for branch in branches if _is_entity_shape(branch))
                return
        if _is_entity_shape(node):
            found.append(node)
            return
        for value in node.values():
            visit(value)

    visit(schema)
    return found


def _shape_properties(schema: Any) -> tuple[str, ...]:
    """The property names an entity may carry, in the schema's own order.

    The class slot and the id slot are left out. Neither was ever the property
    step's to choose: the first is what the plan decided and the second is how
    the answer is joined back to it.
    """
    names: list[str] = []
    for shape in _entity_shapes(schema):
        for name in shape.get("properties") or {}:
            if name not in _CLASS_KEYS and name not in _ID_KEYS and name not in names:
                names.append(name)
    return tuple(names)


def _required_properties(schema: Any) -> set[str]:
    """Every property an entity shape requires, which a trim keeps.

    A required property is not the property step's to remove. Dropping it
    leaves a name in ``required`` with nothing to satisfy it, and a provider
    subset that rewrites ``required`` from ``properties`` would instead make
    the answer legal without it, so the same trim would mean two things.
    """
    names: set[str] = set()
    for shape in _entity_shapes(schema):
        required = shape.get("required")
        if isinstance(required, list):
            names.update(name for name in required if isinstance(name, str))
    return names


def _admitted_properties(
    classes: tuple[str, ...],
    branches: dict[str, dict[str, Any]] | None,
    lineage: dict[str, tuple[str, ...]],
) -> set[str]:
    """Everything the classes on a shortlist declare or inherit.

    Empty when the corpus declares no branches, which the caller reads as no
    narrowing rather than as no properties.
    """
    if not branches:
        return set()
    found: set[str] = set()
    for name in classes:
        seen: set[str] = set()
        queue = [name]
        while queue:
            current = queue.pop()
            if current in seen:
                continue
            seen.add(current)
            found.update(branches.get(current) or {})
            queue.extend(lineage.get(current, ()))
    return found


def _trim_properties(schema: dict[str, Any] | None, keep: set[str]) -> dict[str, Any] | None:
    """The answer shape with the slots the property step left out removed."""
    if schema is None:
        return None
    trimmed = copy.deepcopy(schema)
    for shape in _entity_shapes(trimmed):
        properties = shape.get("properties") or {}
        shape["properties"] = {
            name: definition
            for name, definition in properties.items()
            if name in keep or name in _CLASS_KEYS or name in _ID_KEYS
        }
    return trimmed


def _trim_branches(
    branches: dict[str, dict[str, Any]] | None,
    keep: set[str],
) -> dict[str, dict[str, Any]] | None:
    """The union branches, narrowed the way the answer shape was.

    Trimmed together or not at all. A branch still declaring a property the
    answer shape no longer carries would put that property back on the union
    arm alone, and the difference between the arms would be a difference in
    what each was asked for.
    """
    if not branches:
        return branches
    return {
        name: {prop: definition for prop, definition in properties.items() if prop in keep}
        for name, properties in branches.items()
    }


def _fillable_of(payload: Any, available: dict[str, tuple[str, ...]]) -> dict[str, list[Any]]:
    """The property lists in an answer, whatever the model called the wrapper.

    The declared wrapper first, then a lone key holding an object, then the
    answer itself. The same allowance :func:`_entities_of` makes, and for the
    same observation: giving a schema a title stopped one provider rejecting it
    and started another answering under that title.
    """
    if not isinstance(payload, dict):
        return {}
    candidates: list[dict[str, Any]] = []
    inner = payload.get("fillable")
    if isinstance(inner, dict):
        candidates.append(inner)
    elif len(payload) == 1:
        only = next(iter(payload.values()))
        if isinstance(only, dict):
            candidates.append(only)
    candidates.append(payload)
    for candidate in candidates:
        found = {key: value for key, value in candidate.items() if key in available and isinstance(value, list)}
        if found:
            return found
    return {}


def _accepts_null(slot: Any) -> bool:
    """Whether a prepared slot was left able to say nothing."""
    if not isinstance(slot, dict):
        return False
    declared = slot.get("type")
    return "null" in (declared if isinstance(declared, list) else [declared])


def _entity_id(entity: Any) -> str | None:
    """The id an answered entity states, whatever key it put it under."""
    if not isinstance(entity, dict):
        return None
    for key in _ID_KEYS:
        value = entity.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _descends(name: str, admitted: set[str], lineage: dict[str, tuple[str, ...]]) -> bool:
    """Whether a class is one of these or inherits from one."""
    seen: set[str] = set()
    queue = [name]
    while queue:
        current = queue.pop()
        if current in admitted:
            return True
        if current in seen:
            continue
        seen.add(current)
        queue.extend(lineage.get(current, ()))
    return False


def _compatible_ids(
    plan: tuple[PlannedEntity, ...],
    ranges: tuple[str, ...],
    lineage: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    """The planned entities a property with this range may point at.

    A shortlist counts when any class on it fits, because the fill step has
    not committed to one yet and offering only the first would rule out a
    target the second call may well answer with.
    """
    admitted = set(ranges)
    return tuple(
        dict.fromkeys(
            entity.key for entity in plan if any(_descends(name, admitted, lineage) for name in entity.classes)
        )
    )


def _edges_of(
    entities: list[Any],
    ranges: dict[str, tuple[str, ...]] | None,
) -> tuple[list[Edge], list[Edge]]:
    """Every edge the answer asserted, and the ones reaching nothing.

    Read from the entities that state an id. One that states none is not in
    the plan and its links have no source to hang from; the id slot is
    required and enumerated, so an answer without one is a decode failure
    already and is reported as that rather than twice.
    """
    if not ranges:
        return [], []
    emitted = {found for entity in entities if (found := _entity_id(entity)) is not None}
    links: list[Edge] = []
    dangling: list[Edge] = []
    for entity in entities:
        source = _entity_id(entity)
        if source is None:
            continue
        for name in ranges:
            value = entity.get(name)
            for item in value if isinstance(value, list) else [value]:
                if not isinstance(item, str) or not item.strip():
                    continue
                edge = Edge(source=source, prop=name, target=item.strip())
                links.append(edge)
                if edge.target not in emitted:
                    dangling.append(edge)
    return links, dangling


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
    """The entity list in an answer, whatever the model called the wrapper.

    The named wrappers are tried first. After them comes the case the names
    cannot cover: a model that titles its answer after the schema. Naming the
    selection schema ``EntityCandidates`` stopped one provider rejecting it and
    started another answering ``{"EntityCandidates": [...]}``, correct entities
    under a key no list could hold. So a lone key whose value is a list of
    objects is read as the wrapper it plainly is.
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for wrapper in ("entities", "instances", "items", "results"):
            value = payload.get(wrapper)
            if isinstance(value, list):
                return value
        if len(payload) == 1:
            only = next(iter(payload.values()))
            if isinstance(only, list) and all(isinstance(item, dict) for item in only):
                return only
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
