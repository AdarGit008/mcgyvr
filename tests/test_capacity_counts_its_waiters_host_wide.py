"""A capacity can say how many dispatches are queued for a rig, across processes.

The promise: given a gauge, a dispatch that has to *wait* for a slot is counted
for exactly as long as it waits, by anyone on this host who asks
(:meth:`~mcgyvr.capacity.Capacity.waiting`); and given none, nothing changes.

* **Only a dispatch that has to wait is demand.** One that is granted a slot at
  once is never counted — not for an instant — because a reader that saw it
  would read a busy rig as a queued one.
* **A drain is not demand.** :meth:`~mcgyvr.capacity.Capacity.drain` waits for
  every slot so that a card can be taken down; counting it would make the act of
  sleeping a rig look like pressure to wake it.
* **A gauge is optional and a missing one is not an error.** Without it
  ``waiting`` is ``None`` — no reading, which is not zero — and no gauge
  directory is made or written, so a capacity built the way every caller built
  one before is byte-for-byte what it was.

Every directory is under ``tmp_path`` and every host is invented.
"""

from __future__ import annotations

import threading
import time
from contextlib import AbstractContextManager
from pathlib import Path

import pytest

import mcgyvr.pressure as pressure
from mcgyvr.capacity import Capacity, CapacityError, SlotUnavailableError
from mcgyvr.local_pool import Endpoint, Protocol
from mcgyvr.pressure import Gauge

URL = "http://fast-box.example:8000"


def endpoint(limit: int = 1, source: str = "fast") -> Endpoint:
    return Endpoint(
        source=source,
        base_url=URL,
        protocol=Protocol.OPENAI,
        max_parallel=limit,
        credential_env=None,
    )


def capacity_for(tmp_path: Path, gauge: Gauge | None) -> Capacity:
    return Capacity(
        {"fast": 1},
        lock_dir=tmp_path / "slots",
        urls={"fast": URL},
        gauge=gauge,
    )


def until(what: str, done: object) -> None:
    deadline = time.monotonic() + 30
    while not done():  # type: ignore[operator]
        assert time.monotonic() < deadline, f"never saw: {what}"
        time.sleep(0.01)


def test_a_dispatch_that_must_wait_is_counted_while_it_waits_and_not_after(
    tmp_path: Path,
) -> None:
    capacity = capacity_for(tmp_path, Gauge(tmp_path / "gauge"))
    granted = threading.Event()
    finish = threading.Event()

    def queued() -> None:
        with capacity.hold(endpoint()):
            granted.set()
            finish.wait(timeout=30)

    with capacity.hold(endpoint()):
        assert capacity.waiting("fast") == 0, "the holder was granted at once"
        waiter = threading.Thread(target=queued)
        waiter.start()
        until("the waiter queued", lambda: capacity.waiting("fast") == 1)
        assert not granted.is_set()
    until("the waiter was granted", granted.is_set)
    assert capacity.waiting("fast") == 0, "granted, it is no longer waiting"
    finish.set()
    waiter.join(timeout=30)
    assert capacity.waiting("fast") == 0


def test_several_waiters_are_each_counted(tmp_path: Path) -> None:
    capacity = capacity_for(tmp_path, Gauge(tmp_path / "gauge"))
    finish = threading.Event()

    def queued() -> None:
        with capacity.hold(endpoint()):
            finish.wait(timeout=30)

    with capacity.hold(endpoint()):
        waiters = [threading.Thread(target=queued) for _ in range(3)]
        for each in waiters:
            each.start()
        until("three queued", lambda: capacity.waiting("fast") == 3)
    finish.set()
    for each in waiters:
        each.join(timeout=30)
    assert capacity.waiting("fast") == 0


def test_a_dispatch_that_gets_a_slot_at_once_is_never_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gauge = Gauge(tmp_path / "gauge")
    capacity = capacity_for(tmp_path, gauge)
    marked: list[str] = []
    made = gauge.present

    def spying(key: str) -> AbstractContextManager[None]:
        marked.append(key)
        return made(key)

    monkeypatch.setattr(gauge, "present", spying)

    with capacity.hold(endpoint()):
        assert capacity.waiting("fast") == 0
    with capacity.hold(endpoint()):
        pass

    assert marked == [], "no waiting was ever announced"


def test_a_claim_with_no_queueing_is_refused_without_ever_being_counted(
    tmp_path: Path,
) -> None:
    capacity = capacity_for(tmp_path, Gauge(tmp_path / "gauge"))
    outcome: list[object] = []

    def claim() -> None:
        try:
            with capacity.hold(endpoint(), timeout=0):
                outcome.append("granted")  # pragma: no cover
        except SlotUnavailableError:
            outcome.append(capacity.waiting("fast"))

    with capacity.hold(endpoint()):
        thread = threading.Thread(target=claim)
        thread.start()
        thread.join(timeout=30)

    assert outcome == [0], "refused at once, and the refusal was never a wait"


def test_a_wait_that_ends_in_a_refusal_is_not_counted_afterwards(
    tmp_path: Path,
) -> None:
    capacity = capacity_for(tmp_path, Gauge(tmp_path / "gauge"))
    outcome: list[str] = []

    def claim() -> None:
        try:
            with capacity.hold(endpoint(), timeout=0.3):
                outcome.append("granted")  # pragma: no cover
        except SlotUnavailableError:
            outcome.append("refused")

    with capacity.hold(endpoint()):
        thread = threading.Thread(target=claim)
        thread.start()
        until("the claim queued", lambda: capacity.waiting("fast") == 1)
        thread.join(timeout=30)

    assert outcome == ["refused"]
    assert capacity.waiting("fast") == 0, "the deadline ended the wait and the count"


def test_without_a_gauge_waiting_is_none_and_nothing_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    default = tmp_path / "default-gauge"
    monkeypatch.setattr(pressure, "default_directory", lambda: default)
    capacity = capacity_for(tmp_path, None)
    finish = threading.Event()

    def queued() -> None:
        with capacity.hold(endpoint()):
            finish.wait(timeout=30)

    with capacity.hold(endpoint()):
        thread = threading.Thread(target=queued)
        thread.start()
        time.sleep(0.2)
        assert capacity.waiting("fast") is None, "no gauge, no reading"
    finish.set()
    thread.join(timeout=30)

    assert not default.exists()
    assert not (tmp_path / "gauge").exists()
    assert [p.name for p in (tmp_path).iterdir()] == ["slots"]


def test_a_drain_is_not_counted_as_waiting(tmp_path: Path) -> None:
    capacity = capacity_for(tmp_path, Gauge(tmp_path / "gauge"))
    drained = threading.Event()
    finish = threading.Event()
    seen: list[int | None] = []

    def drain() -> None:
        with capacity.drain(["fast"]):
            drained.set()
            finish.wait(timeout=30)

    with capacity.hold(endpoint()):
        thread = threading.Thread(target=drain)
        thread.start()
        time.sleep(0.3)
        seen.append(capacity.waiting("fast"))
    until("the drain took the slot", drained.is_set)
    seen.append(capacity.waiting("fast"))
    finish.set()
    thread.join(timeout=30)

    assert seen == [0, 0], "a drain waits for the card to empty, and is not demand"


def test_waiting_is_counted_by_other_capacities_on_the_same_rig_and_gauge(
    tmp_path: Path,
) -> None:
    """The count is host-wide: a second capacity — as in a second process — sees
    the queue the first one's dispatches are standing in."""
    gauge = Gauge(tmp_path / "gauge")
    here = capacity_for(tmp_path, gauge)
    elsewhere = capacity_for(tmp_path, Gauge(tmp_path / "gauge"))
    finish = threading.Event()

    def queued() -> None:
        with here.hold(endpoint()):
            finish.wait(timeout=30)

    with elsewhere.hold(endpoint()):
        thread = threading.Thread(target=queued)
        thread.start()
        until("seen from the other capacity", lambda: elsewhere.waiting("fast") == 1)
    finish.set()
    thread.join(timeout=30)


def test_waiting_refuses_a_source_the_capacity_does_not_bound(
    tmp_path: Path,
) -> None:
    capacity = capacity_for(tmp_path, Gauge(tmp_path / "gauge"))

    with pytest.raises(CapacityError, match="no declared capacity for unit 'ghost'"):
        capacity.waiting("ghost")


def test_a_capacity_built_from_a_config_takes_the_gauge_too(tmp_path: Path) -> None:
    from mcgyvr.config import parse

    config = parse(
        "units:\n"
        "  fast:\n"
        f"    address: {URL}\n"
        "    model: qwen2.5-coder-3b\n"
        "    rig: fast-rig\n"
        "    width: 1\n"
        "ladder:\n"
        "- fast\n"
        "profile: dev\n"
    )

    with_gauge = Capacity.of(config, root=tmp_path / "a", gauge=Gauge(tmp_path / "g"))
    without = Capacity.of(config, root=tmp_path / "b")

    assert with_gauge.waiting("fast") == 0
    assert without.waiting("fast") is None
