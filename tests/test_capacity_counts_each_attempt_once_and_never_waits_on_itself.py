"""Capacity counts one attempt once and never waits on a slot it holds itself.

Two defects of one kind: a count or a lock keyed by the wrong identity.

* Slot files are keyed by the unit's address, and two units may name one
  address. :meth:`Capacity.drain` opened each unit's files separately, so the
  second ``flock`` on a file this process already held waited on itself — with
  no timeout, forever. :meth:`Capacity.hold`'s nested-hold guard was keyed by
  unit, so it missed the same case.
* A reservation was recognised only on the thread that took it, while ``drive``
  sends every draw through :func:`~mcgyvr.capacity.run_batch` worker threads.
  One reserved attempt in flight then read as two load, so a width-2 rung with
  one attempt on it read as full.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from mcgyvr.capacity import Capacity, CapacityError, run_batch

SHARED = "http://h:8080"


@pytest.fixture(autouse=True)
def isolated_lock_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "mcgyvr.capacity._default_lock_dir", lambda: tmp_path / "capacity-locks"
    )


def test_draining_two_units_that_share_one_address_does_not_wait_on_itself() -> None:
    capacity = Capacity({"a": 1, "b": 1}, urls={"a": SHARED, "b": SHARED})
    entered = threading.Event()

    def drain() -> None:
        with capacity.drain(["a", "b"], timeout=2.0):
            entered.set()

    worker = threading.Thread(target=drain, daemon=True)
    worker.start()
    worker.join(timeout=5.0)

    assert entered.is_set(), "the drain waited on a slot file it already held"


def test_a_drain_of_units_sharing_an_address_still_waits_for_a_dispatch_on_it() -> None:
    capacity = Capacity({"a": 1, "b": 1}, urls={"a": SHARED, "b": SHARED})

    with (
        capacity.hold("a"),
        pytest.raises(CapacityError),
        capacity.drain(["a", "b"], timeout=0.2),
    ):
        pass


def test_holding_a_second_unit_on_the_same_address_is_refused_not_deadlocked() -> None:
    capacity = Capacity({"a": 1, "b": 1}, urls={"a": SHARED, "b": SHARED})

    # A finite timeout only so that a regression fails rather than hangs: the
    # guard must refuse before any wait, which is what the message says.
    with (
        capacity.hold("a"),
        pytest.raises(CapacityError) as caught,
        capacity.hold("b", timeout=0.5),
    ):
        pass

    assert "already holds" in str(caught.value)


def test_a_reserved_attempt_dispatched_through_run_batch_counts_once() -> None:
    capacity = Capacity({"a": 2})
    seen: list[int] = []

    def draw(held: Capacity) -> None:
        with held.hold("a"):
            seen.append(held.load("a"))

    with capacity.reserving("a"):
        outcomes = run_batch([draw], capacity)

    assert all(outcome.ok for outcome in outcomes), outcomes
    assert seen == [1], "one reserved attempt in flight read as more than one load"


def test_two_draws_of_one_reserved_attempt_count_as_two_slots_not_three() -> None:
    capacity = Capacity({"a": 2})
    both = threading.Barrier(2, timeout=5.0)
    seen: list[int] = []

    def draw(held: Capacity) -> None:
        with held.hold("a"):
            both.wait()
            seen.append(held.load("a"))
            both.wait()

    with capacity.reserving("a"):
        outcomes = run_batch([draw, draw], capacity)

    assert all(outcome.ok for outcome in outcomes), outcomes
    assert seen == [2, 2]
