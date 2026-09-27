"""A :class:`~oold.agent.client.ChatClient` over LangChain.

One bundled adapter, so the package is usable without writing one. It stays
the only one, so the protocol is not shaped around LangChain. Provider
packages are not declared here, because a consumer installs the LangChain
integration for the provider it uses.

Requires the ``agent`` extra.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel

from oold.agent.client import ChatResponse, Message, TokenUsage

__all__ = ["LangChainClient", "fold_system_into_user", "usage_from_message"]


def fold_system_into_user(messages: Sequence[Message]) -> list[tuple[str, str]]:
    """Put the system content at the top of the first user turn.

    Some deployments accept a system message, return 200, and drop it. The
    token count shows it: a prompt carrying a schema arrives counted at five
    tokens, and the model answers as if it had been asked nothing. If this
    goes unnoticed, the study reports the model failing a task it was never
    given.

    Folding is declared per model and recorded, never applied on a guess,
    because it changes the prompt and the prompt is part of the treatment.
    """
    system = "\n\n".join(m.content for m in messages if m.role == "system")
    rest = [m for m in messages if m.role != "system"]
    if not system or not rest:
        return [(m.role, m.content) for m in messages]
    first, *others = rest
    folded = f"{system}\n\n{first.content}"
    return [(first.role, folded)] + [(m.role, m.content) for m in others]


def usage_from_message(message: Any) -> TokenUsage:
    """Read token counts off a LangChain message.

    LangChain normalizes providers into ``usage_metadata``, but the nested
    detail dictionaries are optional and differ by provider, so every lookup
    is defensive. A provider that reports nothing yields zeros instead of
    raising, and a zero total means the provider sent no token counts.
    """
    metadata = getattr(message, "usage_metadata", None) or {}
    input_details = metadata.get("input_token_details") or {}
    output_details = metadata.get("output_token_details") or {}
    return TokenUsage(
        input_tokens=int(metadata.get("input_tokens") or 0),
        output_tokens=int(metadata.get("output_tokens") or 0),
        cached_input_tokens=int(input_details.get("cache_read") or 0),
        reasoning_tokens=int(output_details.get("reasoning") or 0),
    )


class LangChainClient:
    """Adapt a LangChain chat model to the :class:`ChatClient` protocol."""

    def __init__(self, llm: BaseChatModel, model: str, *, fold_system: bool = False) -> None:
        self._llm = llm
        self.model = model
        """The identifier recorded in the result. Passed in instead of read
        off the object: the provider's model name and the deployment name are
        different strings, and the result needs the one that identifies the
        weights."""
        self.fold_system = fold_system
        """Whether the system content is folded into the first user turn.
        Set for deployments that discard a system message without saying so.
        Recorded, because it changes the prompt the model was sent."""

    @property
    def llm(self) -> BaseChatModel:
        """The wrapped chat model, so a caller can check what it was built with."""
        return self._llm

    def invoke(
        self,
        messages: Sequence[Message],
        *,
        response_format: dict[str, Any] | None = None,
    ) -> ChatResponse:
        llm: Any = self._llm
        parsed: dict[str, Any] | None = None
        turns = fold_system_into_user(messages) if self.fold_system else [(m.role, m.content) for m in messages]

        if response_format is not None:
            structured = llm.with_structured_output(response_format, include_raw=True)
            result = structured.invoke(turns)
            raw = result.get("raw") if isinstance(result, dict) else None
            parsing_error = result.get("parsing_error") if isinstance(result, dict) else None
            if parsing_error is not None:
                raise ValueError(f"structured output did not parse: {parsing_error}")
            parsed = result.get("parsed") if isinstance(result, dict) else None
            if parsed is not None and not isinstance(parsed, dict):
                parsed = dict(parsed)
            text = getattr(raw, "content", "") or ""
            return ChatResponse(
                text=text if isinstance(text, str) else str(text),
                parsed=parsed,
                usage=usage_from_message(raw),
                raw=raw,
            )

        reply = llm.invoke(turns)
        content = getattr(reply, "content", reply)
        return ChatResponse(
            text=content if isinstance(content, str) else str(content),
            parsed=None,
            usage=usage_from_message(reply),
            raw=reply,
        )
