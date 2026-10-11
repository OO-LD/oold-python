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

from oold.agent.client import (
    ChatResponse,
    Message,
    TokenUsage,
    fold_system_into_user,
)

__all__ = ["LangChainClient", "fold_system_into_user", "usage_from_message"]


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

    def __init__(self, llm: BaseChatModel, model: str, *, fold_system: bool = False, cache_prefix: bool = True) -> None:
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
        self.cache_prefix = cache_prefix
        """Whether the system turn is marked for the provider to cache.

        On, because an extraction sends the same catalogue and the same schema
        in front of every call of a run while only the question after them
        changes, and that prefix is most of the request: one recipe page cost
        140,532 input tokens over six calls, of which the document was about
        1,700.

        Only Anthropic needs the mark. OpenAI caches a long prefix by itself
        and vLLM does it server side, so the flag reaches only the client that
        would otherwise re-read the prefix every time. A model that does not
        understand the block form is never given it."""

    @property
    def llm(self) -> BaseChatModel:
        """The wrapped chat model, so a caller can check what it was built with."""
        return self._llm

    def _turns(self, messages: Sequence[Message]) -> list[Any]:
        """The turns as the provider takes them.

        Role and content pairs, except where the system turn is marked for
        caching: that needs a content block rather than a string, which only
        the providers that read the mark accept.
        """
        if self.fold_system:
            return list(fold_system_into_user(messages))
        pairs: list[Any] = [(m.role, m.content) for m in messages]
        if not self._marks_a_cacheable_prefix():
            return pairs
        marked: list[Any] = []
        for role, content in pairs:
            if role == "system" and content:
                block = {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
                marked.append((role, [block]))
            else:
                marked.append((role, content))
        return marked

    def _marks_a_cacheable_prefix(self) -> bool:
        """Whether this provider reads a cache mark on a content block.

        Decided from the model object rather than configured, so a caller that
        builds a client has nothing to remember. Anthropic is the one that
        needs telling; the others cache a repeated prefix on their own.
        """
        if not self.cache_prefix:
            return False
        return "anthropic" in type(self._llm).__module__.lower()

    def invoke(
        self,
        messages: Sequence[Message],
        *,
        response_format: dict[str, Any] | None = None,
        strict: bool = False,
    ) -> ChatResponse:
        llm: Any = self._llm
        parsed: dict[str, Any] | None = None
        turns = self._turns(messages)

        if response_format is not None:
            # strict=False sends the schema and applies no grammar, which is
            # the default and was never set. An arm that asked for a decode
            # constraint got a hint; 589 recorded cells answered outside an
            # enum the arm had pinned.
            structured = llm.with_structured_output(response_format, include_raw=True, strict=strict or None)
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
