"""A cancelled ride reports what the host's unit made, as a head's relay does.

A rider who leaves mid-answer has the hub cancel the ride. The rig hangs up
on the unit at once, as before, and now says in its ``relay_end`` what the
unit made by then (``tokens_in``, ``tokens_out``), so the hub can charge the
rider and pay the host exactly that instead of an estimate: just before it
hangs up, on a thread of its own, the agent reads the unit's own status page
(llama.cpp's ``/slots``, at the root of the address the ride posts to) the
way it reads a head's
(``tests/test_a_cancelled_relay_reports_what_its_head_made_before_the_agent_hangs_up.py``):
the same reading of the slot's counts, the same off-by-one allowance, the
same rule that in any doubt the ride ends as it always did, ``cancelled`` and
no counts, and the hub keeps to what it did before. It is never an error.

The unit is the host's own and the host uses it too, so the doubt is wider
than a head's: a unit that may not be llama.cpp (no such page, or one that
answers differently), another ride on the unit, the host's own request at
work beside the ride's (a second slot at work, since a ride is admitted only
while a slot is free and the host always keeps one), an answer the unit has
already given, a page that is slow. Each of those ends with no counts.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes
from tests.test_a_cancelled_relay_reports_what_its_head_made_before_the_agent_hangs_up import (  # noqa: E501
    CANCELLED,
    ENDLESS,
    IDLE,
    MADE,
    PAGES,
    Head,
    Heads,
    Rig,
    _serve,
    busy,
)


@dataclass
class Shared:
    """The one unit this host shares, at an address spelled with ``/v1``."""

    port: int
    rider_cap: int = 1

    def url(self, endpoint: str) -> str:
        return f"http://127.0.0.1:{self.port}/v1/chat/completions"


class Units:
    def __init__(self, unit: Shared) -> None:
        self.unit = unit

    def advertised(self, unit_id: str) -> Shared | None:
        return self.unit if unit_id == "u1" else None

    def ride(self, unit_id: str) -> Any:
        return nullcontext()


class Host(Rig):
    """A rig whose unit is shared: ``head`` is that unit's server."""

    def ride(self, request_id: str = "q1", *, stream: bool = True) -> None:
        body = b'{"messages": []}'
        self.send(
            "unit_relay_request",
            f"r-{request_id}",
            unit_id="u1",
            request_id=request_id,
            endpoint="chat_completions",
            body_bytes=len(body),
            stream=stream,
            timeout_s=20,
            max_response_bytes=1 << 20,
            window=64,
        )
        self.send(
            "relay_data",
            f"d-{request_id}",
            request_id=request_id,
            seq=0,
            data_b64=base64.b64encode(body).decode(),
        )
        assert self.head.asked.acquire(timeout=5.0)  # the unit has the request


def _host(unit: Head, rider_cap: int = 1) -> Host:
    from mcgyvr.rig import commands, relay

    unit.server = _serve(unit)
    box = fakes.Box()
    relays = relay.Relays(
        heads=Heads(0),
        send=box.put,
        units=Units(Shared(unit.port, rider_cap)),
    )
    dispatcher = commands.Dispatcher()
    relay.register(dispatcher, relays)
    return Host(unit, box, relays, dispatcher)


@pytest.fixture
def host() -> Iterator[Host]:
    built = _host(Head())
    yield built
    built.head.page_free.set()
    built.relays.cancel_all()
    assert built.head.server is not None
    built.head.server.shutdown()


def test_a_ride_cancelled_mid_answer_says_what_the_units_slot_made(host: Host) -> None:
    host.ride()
    host.answering()
    host.cancel()
    assert host.ended() == MADE  # and the frame is the hub's schema's (the box)
    assert host.head.seen("hung up")
    # the page is the unit's root's, not under its address's ``/v1``, read
    # first and then hung up: once it hangs up the slot is no longer at work
    assert host.head.events == ["GET /slots", "hung up"]


def test_a_ride_not_streamed_cancelled_while_the_unit_works_says_it_too(
    host: Host,
) -> None:
    host.head.answers_first = False
    host.ride(stream=False)
    host.at_work()
    host.cancel()
    assert host.ended() == MADE
    assert host.head.seen("hung up")
    assert host.head.events == ["GET /slots", "hung up"]
    assert not host.box.of_type("relay_response")


def test_a_ride_not_streamed_is_streamed_from_the_unit_and_read_for_meanwhile(
    host: Host,
) -> None:
    host.head.answers_first = True  # the unit is streaming it, in pieces
    host.ride(stream=False)
    assert host.head.streaming.wait(timeout=5.0)
    host.at_work()
    host.cancel()
    assert host.ended() == MADE
    assert host.head.seen("hung up")
    assert not host.box.of_type("relay_response")


#: A unit that is not llama.cpp, or that the host is using too, among the
#: pages a head's relay also reads for nothing.
UNITS = {
    "no such page": PAGES["no such page"],
    "the page is turned off": PAGES["the page is turned off"],
    "another engine's page": PAGES["not json"],
    "the host's own request at work beside the ride's": PAGES["two slots at work"],
    "no slot at work": PAGES["no slot at work"],
    "a prompt not counted yet": PAGES["a prompt not counted yet"],
}


@pytest.mark.parametrize("why", UNITS)
def test_a_unit_that_does_not_say_for_certain_leaves_the_end_as_it_was(
    host: Host, why: str
) -> None:
    host.head.page_status, host.head.page = UNITS[why]
    host.ride()
    host.answering()
    host.cancel()
    assert host.ended() == CANCELLED
    assert host.head.seen("hung up")


def test_a_slow_page_is_not_waited_for(
    host: Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As a head's relay: the ride ends while the unit's page is still held."""
    from mcgyvr.rig import relay

    monkeypatch.setattr(relay, "REPORT_WAIT_S", 0.2)
    host.head.page_held = True  # never answered while the test runs
    host.head.chunks = ENDLESS
    host.ride()
    host.answering()
    host.cancel()
    assert host.ended() == CANCELLED
    assert not host.head.page_free.is_set()  # the end did not wait for the page
    assert host.head.seen("hung up")


def test_the_agents_thread_never_waits_for_the_page(
    host: Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As a head's relay: the handler is back while the unit's page is read."""
    from mcgyvr.rig import relay

    monkeypatch.setattr(relay, "REPORT_WAIT_S", 60.0)  # held: no giving up
    host.head.page_held = True
    host.head.chunks = ENDLESS
    host.ride()
    host.answering()
    host.cancel()  # the handler, on the thread that hears the hub
    assert host.head.seen("GET /slots")  # the page is being read meanwhile
    assert not host.box.of_type("relay_end")  # and the ride waits for it
    host.head.page_free.set()
    assert host.ended() == MADE
    assert host.head.seen("hung up")


def test_with_another_ride_on_the_unit_no_slot_is_this_rides_for_certain() -> None:
    built = _host(Head(page=json.dumps([busy(), IDLE, IDLE]).encode()), rider_cap=2)
    try:
        built.ride("q1")
        built.ride("q2")
        built.cancel("q1")
        assert built.ended("q1") == CANCELLED
        built.at_work("q2")
        built.cancel("q2")  # alone on its unit now: its slot is the one at work
        assert built.ended("q2") == MADE | {"request_id": "q2"}
    finally:
        built.relays.cancel_all()
        assert built.head.server is not None
        built.head.server.shutdown()


def test_a_ride_that_ends_some_other_way_reports_nothing(host: Host) -> None:
    host.ride()
    host.answering()
    host.relays.cancel_all()  # the hub is gone: nobody to tell
    assert host.ended() == CANCELLED
    assert "GET /slots" not in host.head.events
