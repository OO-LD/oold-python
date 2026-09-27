"""Handing an invalid answer back with the reasons it failed.

The validator's own wording goes to the model unchanged. Rewriting the errors
into advice would make a repair rate a measure of how well that advice was
phrased, which is a different study from whether a schema helps.
"""

from __future__ import annotations

from collections.abc import Sequence

from oold.agent.client import Message

__all__ = ["repair_message"]

_REPAIR = (
    "That answer does not satisfy the schema. Correct it and answer again "
    "with the corrected JSON only.\n\nWhat you sent:\n{answer}\n\nWhat failed:\n{errors}"
)


def repair_message(answer: str, errors: Sequence[str], limit: int = 12) -> Message:
    """One user turn carrying the failed answer and the validator's reasons.

    Capped, because a wide schema can fail on every property of every entity
    and a thousand near-identical lines would crowd out the answer itself.
    """
    listed = "\n".join(f"- {reason}" for reason in list(errors)[:limit])
    if len(errors) > limit:
        listed += f"\n- and {len(errors) - limit} more"
    return Message(role="user", content=_REPAIR.format(answer=answer, errors=listed))
