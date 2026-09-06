"""§4 — a success during a cooldown does not cancel the sentence.

The pressure test's T1-F found that :meth:`~mcgyvr.cooldown.Cooldown.record_success`
popped the *whole* record, ``until`` included. Two consequences, both on the
single-host install that is the common one:

* three consecutive failures never accumulate when a healthy rung's successes
  interleave with a broken rung's failures — the streak is reset before it
  reaches the threshold; and
* a success that lands *after* the cooldown is armed (an in-flight dispatch from
  a parallel wave) deletes the sentence at t=0, so a source that earned a
  60-second removal is offered again immediately.

The fix is the one the reporter named: ``record_success`` resets ``failures``
but leaves an armed ``until`` in place. A success that arrives while the source
is not cooling still clears the streak, which is what makes the count
*consecutive*.
"""

from __future__ import annotations

from mcgyvr.availability import AvailabilityVerdict
from mcgyvr.cooldown import Cooldown
from mcgyvr.pool import Endpoint, Protocol


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _live(endpoint: Endpoint, timeout_s: float) -> AvailabilityVerdict:
    """Always-live probe, so removal can only come from the failure record."""
    return AvailabilityVerdict(
        source=endpoint.source,
        live=True,
        reason="",
        how="stub probe, no network",
        elapsed_s=0.0,
    )


def _endpoint() -> Endpoint:
    return Endpoint(
        source="workbench",
        base_url="http://127.0.0.1:11434",
        protocol=Protocol.OPENAI,
        max_parallel=2,
        credential_env=None,
    )


def _cooldown(clock: _Clock) -> tuple[Cooldown, Endpoint]:
    return Cooldown(probe=_live, clock=clock, cooldown_s=60.0), _endpoint()


def test_a_success_while_not_cooling_still_clears_the_streak() -> None:
    """The count is *consecutive*: an unarmed success resets failures to zero."""
    clock = _Clock()
    tracker, endpoint = _cooldown(clock)

    tracker.record_failure(endpoint.source)
    tracker.record_failure(endpoint.source)
    tracker.record_success(endpoint.source)

    # Two failures, then a success: the streak is over, and a single later
    # failure must not arm the cooldown.
    tracker.record_failure(endpoint.source)
    assert tracker.unavailable([endpoint]) == {}, (
        "a single failure after an intervening success took the source out"
    )


def test_a_success_does_not_cancel_an_armed_cooldown() -> None:
    """Three failures arm the sentence; a later success must not release it.

    The success is an in-flight dispatch started before the failures, so it is
    not evidence the source recovered. The count resets, the ``until`` stands.
    """
    clock = _Clock()
    tracker, endpoint = _cooldown(clock)

    for _ in range(3):
        tracker.record_failure(endpoint.source)
    assert endpoint.source in tracker.unavailable([endpoint]), (
        "three consecutive failures did not take the source out"
    )

    tracker.record_success(endpoint.source)
    assert endpoint.source in tracker.unavailable([endpoint]), (
        "a success cancelled a cooldown that three failures had earned"
    )


def test_the_sentence_is_served_and_then_released_with_a_clean_count() -> None:
    """The success resets the count, so the post-cooldown source starts fresh."""
    clock = _Clock()
    tracker, endpoint = _cooldown(clock)

    for _ in range(3):
        tracker.record_failure(endpoint.source)
    tracker.record_success(endpoint.source)

    clock.advance(61.0)  # past the cooldown
    assert tracker.unavailable([endpoint]) == {}, (
        "the source never came back after its cooldown elapsed"
    )

    # The count was reset by the success, so one failure after release must not
    # immediately re-arm.
    tracker.record_failure(endpoint.source)
    assert tracker.unavailable([endpoint]) == {}, (
        "the pre-cooldown failures were not cleared: one new failure re-armed "
        "the source"
    )
