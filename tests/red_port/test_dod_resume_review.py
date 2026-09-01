"""S9 — ``pending.resume`` must read a review's three states, not collapse them.

``resume`` typed its verifier seam as ``Callable[[str], bool]`` and read
``bool(verify(content))``, but the verifier it exists to wrap —
:func:`mcgyvr.verify.verify` — returns a three-state
:class:`~mcgyvr.escalate.Review`: agreed, refused, or *unusable*. A
:class:`Review` has no ``__bool__``, so ``bool`` reads every one of them as
``True`` and a verifier that could not be reached, or that refused, is treated
as an approval and the work is delivered.

The fix reads the opinion directly: an unusable review is reported as
"unreachable" and a refusal as "declined", and only agreement reaches delivery.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcgyvr.escalate import Review
from tests.red_port.conftest import required

RESUME = "resume stashed work once verification is reachable again"

GOOD = 'def fetch(url):\n    return "café " + url\n'


def _resume() -> Any:
    return required(
        RESUME, lambda: __import__("mcgyvr.pending", fromlist=["resume"]).resume
    )


def _stash() -> Any:
    return required(
        "stash gate-passed work that could not be verified, in a form that can "
        "resume it",
        lambda: __import__("mcgyvr.pending", fromlist=["stash"]).stash,
    )


def test_an_unusable_review_is_unreachable_not_a_refusal(
    repo: Path, contract: Any, tmp_path: Path
) -> None:
    """A verifier that could not be asked must not read as an approval or a decline."""
    store = tmp_path / "pending"
    _stash()(store=store, repo=repo, contract=contract, content=GOOD)

    result = _resume()(
        store=store,
        repo=repo,
        task=contract.id,
        verify=lambda _text: Review.unusable("endpoint down"),
    )

    assert not result.completed, f"an unusable review completed the resume: {result}"
    assert "unreachable" in result.reason, (
        f"an unusable review was not reported as unreachable: {result.reason!r}"
    )


def test_a_refused_review_stays_pending(
    repo: Path, contract: Any, tmp_path: Path
) -> None:
    """A reviewer that declined is a decline, not an approval."""
    store = tmp_path / "pending"
    _stash()(store=store, repo=repo, contract=contract, content=GOOD)

    result = _resume()(
        store=store,
        repo=repo,
        task=contract.id,
        verify=lambda _text: Review.refused("fix the retry ceiling"),
    )

    assert not result.completed, f"a refused review completed the resume: {result}"
    assert "declined" in result.reason, (
        f"a refused review was not reported as declined: {result.reason!r}"
    )
