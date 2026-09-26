"""A :class:`~oold.agent.client.ChatClient` over LangChain.

One bundled adapter, so the package is usable without writing one, and only
one, so the abstraction stays honest. Provider packages are not declared here,
because a consumer installs the LangChain integration for the provider it uses.

Requires the ``agent`` extra.
"""

from __future__ import annotations

from typing import Any, Sequence

from langchain_core.language_models import BaseChatModel

from oold.agent.client import ChatResponse, Message, TokenUsage

__all__ = ["LangChainClient", "usage_from_message"]


def usage_from_message(message: Any) -> TokenUsage:
    """Read token counts off a LangChain message.

    LangChain normalises providers into ``usage_metadata``, but the nested
    detail dictionaries are optional and differ by provider, so every lookup
    is defensive. A provider that reports nothing yields zeros rather than
    raising, and a zero total is the signal that a model is uninstrumented.
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

    def __init__(self, llm: BaseChatModel, model: str) -> None:
        self._llm = llm
        self.model = model
        """The identifier recorded in the result. Passed in rather than read
        off the object, because what a provider calls a model and what a
        deployment is named are different strings and the result needs the
        one that identifies the weights."""

    def invoke(
        self,
        messages: Sequence[Message],
        *,
        response_format: dict[str, Any] | None = None,
    ) -> ChatResponse:
        llm: Any = self._llm
        parsed: dict[str, Any] | None = None

        if response_format is not None:
            structured = llm.with_structured_output(
                response_format, include_raw=True
            )
            result = structured.invoke(
                [(m.role, m.content) for m in messages]
            )
            raw = result.get("raw") if isinstance(result, dict) else None
            parsing_error = (
                result.get("parsing_error") if isinstance(result, dict) else None
            )
            if parsing_error is not None:
                raise ValueError(
                    f"structured output did not parse: {parsing_error}"
                )
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

        reply = llm.invoke([(m.role, m.content) for m in messages])
        content = getattr(reply, "content", reply)
        return ChatResponse(
            text=content if isinstance(content, str) else str(content),
            parsed=None,
            usage=usage_from_message(reply),
            raw=reply,
        )
