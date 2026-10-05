"""A ride is admitted while the unit has a free slot: the host first.

A shared unit of width ``W`` lends at most ``rider_slots`` (``R``) of its slots
to riders. A ride is admitted when the unit has a slot free now — the host's
own requests in flight plus the rides in flight are fewer than ``W`` — and
fewer than ``R`` rides are in flight. A host busy on some of its slots still
lends a free one; before, a ride was admitted only while the host left
``R`` slots untouched, so a unit of two slots lending one took a ride only
while the host had nothing in flight.

The host's own requests are never refused for a ride beyond what ``R`` allows:
riders hold at most ``R`` slots, so ``W - R`` are the host's whatever rides
run, and a request of the host's that arrives while a ride runs is served on
any slot that is free.

The rig decides this, by its unit's own count at the moment of the ride; what
the hub believed when it sent the ride does not admit it.

The unit is a scripted server on loopback; its in-flight count and the slots'
lock directory are the test's.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.test_a_ride_reaches_only_the_shared_units_own_address_and_the_host_goes_first import (  # noqa: E501
    Host,
    _body,
    _host,
)


@pytest.fixture
def host(tmp_path: Path) -> Iterator[Host]:
    made = _host(tmp_path, width=2, rider_slots=1)
    yield made
    made.unit.release.set()
    made.relays.cancel_all()
    assert made.unit.server is not None
    made.unit.server.shutdown()


def test_a_host_with_one_of_two_slots_busy_takes_a_ride_and_not_a_second(
    host: Host,
) -> None:
    host.unit.hold = True
    host.busy["coder"] = 1  # the host's own request

    host.ride(_body(), "q1")
    host.running(1)

    host.busy["coder"] = 2  # the host's and the ride
    host.ride(_body(), "q2")
    assert host.ended("q2")["error_code"] == "busy"

    host.unit.release.set()
    assert host.ended("q1")["outcome"] == "complete"


def test_a_host_with_every_slot_busy_takes_no_ride(host: Host) -> None:
    host.busy["coder"] = 2

    host.ride(_body())

    assert host.ended()["error_code"] == "busy"
    assert host.unit.seen == []


def test_a_second_ride_is_refused_though_a_slot_is_free(host: Host) -> None:
    host.unit.hold = True
    host.ride(_body(), "q1")
    host.running(1)
    host.busy["coder"] = 1  # the ride alone: one slot is free, and it is the host's

    host.ride(_body(), "q2")

    assert host.ended("q2")["error_code"] == "busy"


def test_a_server_that_does_not_say_what_it_has_in_flight_takes_no_ride(
    host: Host,
) -> None:
    host.busy["coder"] = None

    host.ride(_body())

    assert host.ended()["error_code"] == "busy"
    assert host.unit.seen == []


def test_a_request_of_the_hosts_that_arrives_while_a_ride_runs_is_served(
    host: Host,
) -> None:
    host.unit.hold = True
    host.ride(_body(), "q1")
    host.running(1)

    # The ride holds one slot; the other is free and the host's dispatch takes it.
    with host.capacity.hold("coder", timeout=0):
        # Both are taken now: a ride the hub sends meanwhile finds none.
        host.busy["coder"] = 2
        host.ride(_body(), "q2")
        assert host.ended("q2")["error_code"] == "busy"

    host.unit.release.set()
    assert host.ended("q1")["outcome"] == "complete"


@pytest.mark.parametrize(
    ("width", "rider_slots", "own", "admitted"),
    [
        (4, 2, 0, 2),  # the rider cap, with slots to spare
        (4, 2, 2, 2),  # the host busy on two: the other two are lent
        (4, 2, 3, 1),  # one slot free: one ride
        (4, 2, 4, 0),
        (4, 3, 2, 2),  # the free slots bound it below the cap
    ],
)
def test_rides_take_the_free_slots_up_to_the_rider_cap(
    tmp_path: Path, width: int, rider_slots: int, own: int, admitted: int
) -> None:
    built = _host(tmp_path, width=width, rider_slots=rider_slots)
    try:
        built.unit.hold = True
        taken = 0
        for index in range(4):
            request_id = f"q{index}"
            built.busy["coder"] = own + taken  # the host's and the rides
            built.ride(_body(), request_id)
            if taken < admitted:
                built.running(taken + 1)
                taken += 1
            else:
                assert built.ended(request_id)["error_code"] == "busy"
        assert len(built.unit.seen) == admitted
    finally:
        built.unit.release.set()
        built.relays.cancel_all()
        assert built.unit.server is not None
        built.unit.server.shutdown()
