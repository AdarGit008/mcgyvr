"""D09 — a source that keeps failing stops being offered, and comes back on its own.

mcgyvr knows two things about a source and neither is this one.
:class:`~mcgyvr.availability.Availability` asks "is anything there", once, and caches
the answer for the life of the instance — deliberately, because a run is short and a
re-probe storm at every escalation is the failure it was designed against.
:class:`~mcgyvr.capacity.Capacity` asks "is there room", and bounds how many
dispatches a source carries at once. Between them sits a source that is reachable,
uncontended, and *does not work*: it answers the model-list path, accepts the
connection, takes the slot, and fails the generation. Every rung on it is handed to a
dispatch that will fail the same way, and nothing in the run ever revises the verdict,
because the verdict was reached before the first dispatch and is never asked again.

Three statements, and the third is the one that makes the first two safe to build.

*A source that keeps failing stops being offered* is the lever. It is asserted with a
probe that reports the source **live** throughout, so the only thing that can have
taken the source out is the record of its failures — a test whose probe went down
would pass against today's code and prove nothing. It is asserted a second time on the
probe count, which must not move: the point of learning from failures is that the
knowledge is already paid for. A design that answered this question by re-probing
would spend a connect timeout per escalation, which is the exact cost
:mod:`~mcgyvr.availability` exists to avoid, and no assertion about availability alone
would notice.

The refusal must name the failures, for the reason M2 gives about the dirty tree: a
caller handed a source that is simply missing from the offered set cannot tell "it kept
failing, wait" from "it was never configured" from "the probe said it was down", and
those three want three different responses from whoever reads the run.

*It becomes available again after a cooldown* is what keeps a transient fault from
being a permanent one — a backend restarting, a model being swapped in, a machine
waking. It is held on both sides of the boundary: still out just before the cooldown
elapses, offered again just after. Asserting only the "after" half would pass against
a design that forgot the source the moment anyone looked twice.

*A source that fails once is not taken out* is the negative half, and it is the reason
the first test is not sufficient on its own. A system that dropped a source on its
first hiccup would satisfy every assertion above while being strictly worse than what
mcgyvr has today: one bad generation — a truncated reply, a transient 502, a model
still loading — would cost the whole rest of the ladder on that host. So the count is
asserted at both ends and at neither middle: five consecutive failures is repeated
failure by any threshold worth choosing, one is not, and where between them the line
falls is the port's to measure. A test that pinned the number would freeze a
measurement nobody has taken.

Nothing here touches the network. The probe is the injected seam
:class:`~mcgyvr.availability.Availability` already takes, and the clock is injected for
the same reason — a cooldown asserted by sleeping is a slow test that is also flaky.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr.availability import AvailabilityVerdict
from mcgyvr.pool import Endpoint, Protocol
from tests.red_port.conftest import required

BEHAVIOR = (
    "stop offering a source that keeps failing, without re-probing it, and offer it "
    "again once a cooldown has elapsed"
)

# Long enough that no plausible implementation treats it as already expired, and
# never waited on: the clock below is injected.
COOLDOWN_S = 60.0

# "Repeatedly" is five here and "once" is one, and nothing in this file has an
# opinion about where between them the threshold sits.
REPEATEDLY = 5


def _tracker() -> Any:
    """The thing that holds per-source failure history for a run.

    Placeholder path, as :func:`~tests.red_port.conftest.required` documents. What is
    being asked for is a liveness view that also learns from dispatch failures — it
    answers ``unavailable`` the way :class:`~mcgyvr.availability.Availability` does, so
    :func:`mcgyvr.pool.source_map` needs to learn nothing new.
    """
    return required(
        BEHAVIOR,
        lambda: __import__("mcgyvr.cooldown", fromlist=["Cooldown"]).Cooldown,
    )


class _Clock:
    """A hand-wound monotonic clock, so a cooldown is asserted rather than waited on."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _LiveProbe:
    """A probe that always reports the source healthy, and counts what it was asked.

    Always-live is the load-bearing part: it removes the one other explanation for a
    source disappearing, so any removal these tests see came from the failure record.
    """

    def __init__(self) -> None:
        self.asked: list[str] = []

    def __call__(self, endpoint: Endpoint, timeout_s: float) -> AvailabilityVerdict:
        self.asked.append(endpoint.source)
        return AvailabilityVerdict(
            source=endpoint.source,
            live=True,
            reason="",
            how="stub probe, no network",
            elapsed_s=0.0,
        )


@pytest.fixture
def endpoint() -> Endpoint:
    """One keyless local source. Constructed, never dialled."""
    return Endpoint(
        source="workbench",
        base_url="http://127.0.0.1:11434",
        protocol=Protocol.OPENAI,
        max_parallel=2,
        credential_env=None,
    )


@pytest.fixture
def probe() -> _LiveProbe:
    return _LiveProbe()


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


def test_a_source_that_keeps_failing_stops_being_offered(
    endpoint: Endpoint, probe: _LiveProbe, clock: _Clock
) -> None:
    """Repeated dispatch failures take a source off the ladder, at no extra probe cost.

    The probe says live before and after; the failures are the only new fact. The probe
    count is asserted unchanged because a source removed by re-probing costs a connect
    timeout at every escalation — the cost :mod:`~mcgyvr.availability` caches to avoid,
    and one an availability-only assertion cannot see.
    """
    tracker = _tracker()(probe=probe, clock=clock, cooldown_s=COOLDOWN_S)

    assert tracker.unavailable([endpoint]) == {}, "a healthy source was not offered"
    already_asked = len(probe.asked)

    for _ in range(REPEATEDLY):
        tracker.record_failure(endpoint.source)

    down = tracker.unavailable([endpoint])
    assert endpoint.source in down, (
        f"{REPEATEDLY} consecutive dispatch failures left the source on the ladder"
    )
    assert len(probe.asked) == already_asked, (
        f"the source was probed again to reach that verdict ({probe.asked}); the "
        f"failures were already paid for"
    )
    assert "fail" in down[endpoint.source].lower(), (
        f"the reason must name the failures, said: {down[endpoint.source]!r}"
    )


def test_a_cooled_down_source_is_offered_again(
    endpoint: Endpoint, probe: _LiveProbe, clock: _Clock
) -> None:
    """A transient fault costs a cooldown, not the rest of the run.

    Held on both sides of the boundary. Asserting only that the source returns
    eventually would pass against a tracker that forgot the failures the moment it was
    asked a second time, which is not a cooldown.
    """
    tracker = _tracker()(probe=probe, clock=clock, cooldown_s=COOLDOWN_S)
    for _ in range(REPEATEDLY):
        tracker.record_failure(endpoint.source)

    assert endpoint.source in tracker.unavailable([endpoint])

    clock.advance(COOLDOWN_S * 0.9)
    assert endpoint.source in tracker.unavailable([endpoint]), (
        "the source came back before its cooldown elapsed"
    )

    clock.advance(COOLDOWN_S * 0.2)
    assert tracker.unavailable([endpoint]) == {}, (
        "the source never came back — a transient fault became a permanent one"
    )


def test_a_source_that_failed_once_is_not_taken_out(
    endpoint: Endpoint, probe: _LiveProbe, clock: _Clock
) -> None:
    """One bad generation is a hiccup, and dropping a host for it is a regression.

    This is the assertion that stops the lever from being implemented as "any failure
    removes the source". Such a design passes the other two tests in this file and is
    worse than mcgyvr today: a single truncated reply or a model still loading would
    cost every remaining rung on that host.
    """
    tracker = _tracker()(probe=probe, clock=clock, cooldown_s=COOLDOWN_S)

    tracker.record_failure(endpoint.source)

    assert tracker.unavailable([endpoint]) == {}, (
        "a single failure took the source off the ladder"
    )
