"""C5 — a reply that cannot be read is a failed review, never an exception.

:func:`~mcgyvr.verify.verify` asks the reviewer inside a ``try``, but reads the
verdict back *outside* it: ``reply = ask(prompt)`` is protected and
``read_verdict(reply)`` is not. An ``ask`` that returns no text — the reviewer
came back empty, or a seam handed back nothing — therefore raises out of
``verify`` where every other bad reply becomes an
:class:`~mcgyvr.escalate.Opinion.UNUSABLE` review.

The fix puts the read inside the same protection as the ask, so a reply that
cannot be read is the same category as a reply that never arrived: no verdict,
reported, not raised.
"""

from __future__ import annotations

from typing import Any

from mcgyvr.catalog import Family
from mcgyvr.escalate import Opinion
from mcgyvr.gate import GateResult
from tests.red_port.conftest import required

BEHAVIOR = (
    "have a fresh-context verifier read a change and turn its reply into a Review"
)

MODEL_FAMILY = Family(name="local", rank=1, doc="a model on the operator's own machine")


def _verify() -> Any:
    return required(
        BEHAVIOR, lambda: __import__("mcgyvr.verify", fromlist=["verify"]).verify
    )


def test_an_ask_that_returns_no_text_is_an_unusable_review_not_a_crash(
    contract: Any,
) -> None:
    """A seam that hands back nothing must not take the whole verify path down."""
    verify = _verify()

    review = verify(
        contract,
        family=MODEL_FAMILY,
        gate=GateResult(),
        change="+    for attempt in range(3):\n",
        builder="qwen2.5-coder:7b",
        reviewer="qwen2.5-coder:32b",
        ask=lambda prompt: None,
        original="def fetch(url):\n    return url\n",
    )

    assert review.opinion is Opinion.UNUSABLE, (
        f"an empty reply was not an unusable review: {review}"
    )
