"""The boundary between the agent and whatever talks to a model.

Two things live here. A :class:`ChatClient` protocol, so the agent depends on a
shape instead of on a vendor SDK, and a :class:`CallLog`, so token cost is
attributed to the step that spent it.

Per-call attribution is not a nicety. A run total cannot separate what the
schema cost from what the instructions cost from what the document cost, which
means the interesting question has to be modelled after the fact instead of
measured. It also hides a whole class of bug, because a counter reset in the
wrong place makes every figure a fraction of the truth while still looking
plausible.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "Call",
    "CallLog",
    "ChatClient",
    "ChatResponse",
    "Message",
    "TokenUsage",
    "fold_system_into_user",
    "prompt_hash",
]


@dataclass(frozen=True)
class Message:
    role: str
    content: str


def fold_system_into_user(messages: Sequence[Message]) -> list[tuple[str, str]]:
    """Put the system content at the top of the first user turn.

    Some deployments accept a system message, return 200, and drop it. The
    token count shows it: a prompt carrying a schema arrives counted at five
    tokens, and the model answers as if it had been asked nothing. If this
    goes unnoticed, the study reports the model failing a task it was never
    given.

    Folding is declared per client, never applied on a guess, because it
    changes the prompt and the prompt is part of the treatment.
    """
    system = "\n\n".join(m.content for m in messages if m.role == "system")
    rest = [m for m in messages if m.role != "system"]
    if not system or not rest:
        return [(m.role, m.content) for m in messages]
    first, *others = rest
    folded = f"{system}\n\n{first.content}"
    return [(first.role, folded)] + [(m.role, m.content) for m in others]


def prompt_hash(messages: Sequence[Message], *, fold_system: bool = False) -> str:
    """Hash of the turns a client sends, not of the document alone.

    Folding changes the bytes one model receives, so a hash taken before it
    would say two models were sent the same prompt when they were not.
    """
    turns = fold_system_into_user(messages) if fold_system else [(m.role, m.content) for m in messages]
    canonical = json.dumps(turns, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TokenUsage:
    """Tokens for one call, with the tiers that are priced differently."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    """Counted inside ``input_tokens``, not in addition to it. Held separately
    because a cached input token costs a fraction of an uncached one, and a
    repeated schema prefix is mostly cache hits."""
    reasoning_tokens: int = 0
    """Counted inside ``output_tokens``. Reasoning models bill these."""

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def billable_input(self) -> int:
        return self.input_tokens - self.cached_input_tokens

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cached_input_tokens=(self.cached_input_tokens + other.cached_input_tokens),
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
        )

    def describe(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total,
        }


@dataclass(frozen=True)
class ChatResponse:
    text: str
    parsed: dict[str, Any] | None = None
    usage: TokenUsage = field(default_factory=TokenUsage)
    raw: Any = None


@runtime_checkable
class ChatClient(Protocol):
    """What the agent needs from a model, and nothing more.

    Implemented here for LangChain. A benchmark or another consumer can
    implement it over any SDK, or over a recording, without this package
    growing a dependency on either.
    """

    model: str

    def invoke(
        self,
        messages: Sequence[Message],
        *,
        response_format: dict[str, Any] | None = None,
        strict: bool = False,
    ) -> ChatResponse: ...


@dataclass(frozen=True)
class Call:
    """One call to a model, as it goes into the result record."""

    step: str
    model: str
    usage: TokenUsage
    elapsed_s: float
    attempt: int = 1
    schema_sha256: str | None = None
    """Hash of the schema actually sent, so a result names the bytes the model
    saw, not the schema someone believes it saw."""
    error: str | None = None

    def describe(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "model": self.model,
            "attempt": self.attempt,
            "elapsed_s": round(self.elapsed_s, 4),
            "schema_sha256": self.schema_sha256,
            "error": self.error,
            **self.usage.describe(),
        }


class CallLog:
    """Every call made during one run, in order.

    Appends are locked because some orchestrations fan out across threads. The
    predecessor of this class worked around that with a per-step buffer merged
    on the main thread, which was correct for the one step that had it and
    silently wrong for the others.
    """

    def __init__(self) -> None:
        self._calls: list[Call] = []
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._calls)

    def __iter__(self) -> Iterator[Call]:
        return iter(tuple(self._calls))

    def append(self, call: Call) -> None:
        with self._lock:
            self._calls.append(call)

    @contextmanager
    def timed(
        self,
        step: str,
        model: str,
        *,
        attempt: int = 1,
        schema_sha256: str | None = None,
    ) -> Iterator[list[TokenUsage]]:
        """Record one call, including one that raises.

        Yields a one-slot list to put the usage into, so a call that fails
        still leaves a record with the error on it. A failed attempt that
        vanishes from the log makes retries look free.
        """
        started = time.monotonic()
        sink: list[TokenUsage] = []
        error: str | None = None
        try:
            yield sink
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self.append(
                Call(
                    step=step,
                    model=model,
                    usage=sink[0] if sink else TokenUsage(),
                    elapsed_s=time.monotonic() - started,
                    attempt=attempt,
                    schema_sha256=schema_sha256,
                    error=error,
                )
            )

    def totals(self) -> TokenUsage:
        total = TokenUsage()
        for call in self._calls:
            total = total + call.usage
        return total

    def by_step(self) -> dict[str, TokenUsage]:
        """Tokens per step, which is the attribution the run total hides."""
        out: dict[str, TokenUsage] = {}
        for call in self._calls:
            out[call.step] = out.get(call.step, TokenUsage()) + call.usage
        return out

    def describe(self) -> dict[str, Any]:
        return {
            "calls": [call.describe() for call in self._calls],
            "totals": self.totals().describe(),
            "by_step": {step: usage.describe() for step, usage in sorted(self.by_step().items())},
            "n_calls": len(self._calls),
            "n_errors": sum(1 for call in self._calls if call.error),
        }
