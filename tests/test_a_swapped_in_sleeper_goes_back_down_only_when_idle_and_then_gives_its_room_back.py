"""A swapped-in sleeper goes back down only when idle, and then gives its room back.

A run that climbs to the RAM sleeper puts the fast rungs down to make its room
and records the swap. Nothing loops in the background to undo it: the next
draw that asks for a fast rung is what gives the room back, and only when the
sleeper is idle and the rung below it is not full — the one reason to wake a
smaller unit again is that the top rungs have nothing to do. Until then the
fast rung is refused with `SwappedOutError` and the climb moves on; it is never
started beside the sleeper, so the card is never asked to hold more than it
has. A swap is made only on a host the live fleet holds, as a wake is.

The card is the one the swap test builds (``test_a_full_top_rung_swaps_...``):
two fast llama.cpp rungs and a RAM rung on one 12 GB card, the floor rung on a
second machine. The door is faked and keeps which containers are up.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcgyvr.capacity import Capacity
from mcgyvr.config import Config
from tests.test_a_full_top_rung_swaps_the_ram_rung_in_and_the_fast_ones_back import (
    CARD_MIB,
    FAST_M,
    FAST_S,
    FLOOR,
    RAM,
    SWAP_HOST,
    containers,
    emitted,
    home,
)

__all__ = ["home"]

PORT = {FAST_S: 8081, FAST_M: 8082, RAM: 8083}


class Card:
    """The swap card behind a faked door: which units are up, every door run, and
    the most memory the up units ever held at once."""

    def __init__(self, config: Config, specs: Path) -> None:
        self.config = config
        named = containers(specs)
        self.unit_of = {named[port]: unit for unit, port in PORT.items()}
        self.room = {unit: config.units[unit].room_mib or 0 for unit in PORT}
        self.up = {FAST_S, FAST_M}
        self.doors: list[str] = []
        self.peak = self.held()

    def held(self) -> int:
        return sum(self.room[unit] for unit in self.up)

    def spawn(self, argv: list[str], **_: Any) -> int:
        verb = argv[argv.index("serve") + 1]
        unit = self.unit_of[argv[argv.index("--unit") + 1]]
        self.doors.append(f"{verb} {unit}")
        if verb in ("up", "wake"):
            self.up.add(unit)
        else:
            self.up.discard(unit)
        self.peak = max(self.peak, self.held())
        return 0

    def send(self, rung: str) -> Any:
        from mcgyvr.runner import RefusedConnectionError

        def sent() -> str:
            if rung not in self.up:
                raise RefusedConnectionError(f"nothing listens for {rung}")
            return f"answered by {rung}"

        return sent


@pytest.fixture
def card(tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch) -> Card:
    import mcgyvr.wake as wake

    config, specs = emitted(tmp_path)
    faked = Card(config, specs)
    monkeypatch.setattr(wake, "spawn_door", faked.spawn)
    monkeypatch.setattr(wake, "saved_card_mib", lambda rigs: {SWAP_HOST: {0: CARD_MIB}})
    return faked


def _capacity(config: Config) -> Capacity:
    from mcgyvr.pressure import Gauge

    return Capacity.of(config, gauge=Gauge())


def _swapped(card: Card) -> Capacity:
    """Run one climb to the RAM rung, which swaps it in, and its capacity."""
    from mcgyvr.wake import for_config

    config = card.config
    capacity = _capacity(config)
    waker = for_config(config)
    assert waker is not None
    assert waker.dispatching(RAM, card.send(RAM), capacity=capacity) == (
        f"answered by {RAM}"
    )
    assert card.up == {RAM}
    return capacity


def test_a_swap_is_recorded_with_the_units_it_put_down(card: Card) -> None:
    from mcgyvr.wake import Swap, known_down, standing_swap

    _swapped(card)

    assert standing_swap(SWAP_HOST) == Swap(sleeper=RAM, displaced=(FAST_S, FAST_M))
    config = card.config
    assert known_down(config, FAST_M) == f"{FAST_M} was put down to make room for {RAM}"
    assert known_down(config, RAM) is None, "the swapped-in sleeper is up"


def test_a_later_run_puts_the_idle_sleeper_down_before_its_room_comes_back(
    card: Card,
) -> None:
    from mcgyvr.wake import for_config, standing_swap

    capacity = _swapped(card)

    # A second run — a waker of its own — asks for a fast rung the swap put down.
    later = for_config(card.config)
    assert later is not None
    assert later.dispatching(FAST_M, card.send(FAST_M), capacity=capacity) == (
        f"answered by {FAST_M}"
    )

    assert card.doors[3:] == [f"down {RAM}", f"up {FAST_S}", f"up {FAST_M}"]
    assert card.peak <= CARD_MIB, "a fast rung was started beside the sleeper"
    assert standing_swap(SWAP_HOST) is None, "the swap was given back"


def test_a_displaced_rung_stays_down_while_its_sleeper_has_work_queued(
    card: Card, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.wake import SwappedOutError, for_config

    capacity = _swapped(card)
    monkeypatch.setattr(capacity, "queued", lambda sources: 2)
    later = for_config(card.config)
    assert later is not None

    with pytest.raises(SwappedOutError, match=f"{RAM} has 2 queued"):
        later.dispatching(FAST_M, card.send(FAST_M), capacity=capacity)
    assert len(card.doors) == 3, "nothing is started or put down"
    assert card.peak <= CARD_MIB


def test_a_displaced_rung_stays_down_while_the_rung_below_the_sleeper_is_full(
    card: Card, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.capacity import Fullness
    from mcgyvr.wake import SwappedOutError, for_config

    capacity = _swapped(card)
    real = capacity.fullness

    def fullness(source: str, rung: str | None = None) -> Fullness:
        if source == FLOOR:
            return Fullness(load=2, server=None, width=2)
        return real(source, rung)

    monkeypatch.setattr(capacity, "fullness", fullness)
    later = for_config(card.config)
    assert later is not None

    with pytest.raises(SwappedOutError, match=f"{FLOOR}, the rung below it, is full"):
        later.dispatching(FAST_S, card.send(FAST_S), capacity=capacity)
    assert len(card.doors) == 3


def test_a_displaced_rung_with_no_capacity_to_read_is_refused_not_started(
    card: Card,
) -> None:
    from mcgyvr.wake import SwappedOutError, for_config

    _swapped(card)
    later = for_config(card.config)
    assert later is not None

    with pytest.raises(SwappedOutError):
        later.dispatching(FAST_M, card.send(FAST_M))
    assert len(card.doors) == 3
    assert card.peak <= CARD_MIB


def test_a_swap_is_not_made_on_a_host_the_live_fleet_does_not_hold(
    card: Card, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mcgyvr.fleet.admit as admit
    import mcgyvr.fleet.roots as roots
    from mcgyvr.runner import RefusedConnectionError
    from mcgyvr.wake import for_config

    monkeypatch.setattr(roots, "runs_live", lambda path: True)
    monkeypatch.setattr(roots, "live_fleet_dir", lambda: tmp_path)
    monkeypatch.setattr(admit, "host_is_locked", lambda root, host: False)
    waker = for_config(card.config)
    assert waker is not None

    with pytest.raises(RefusedConnectionError):
        waker.dispatching(
            RAM,
            card.send(RAM),
            capacity=_capacity(card.config),
        )
    assert card.doors == [], "nothing on an unlocked host is put down"
    assert card.up == {FAST_S, FAST_M}


def test_a_wake_that_fails_says_why(
    card: Card, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mcgyvr.fleet.admit as admit
    import mcgyvr.fleet.roots as roots
    from mcgyvr.ladder_manager import wake_making_room
    from mcgyvr.wake import CardSwitches

    config = card.config
    monkeypatch.setattr(roots, "runs_live", lambda path: True)
    monkeypatch.setattr(roots, "live_fleet_dir", lambda: tmp_path)
    monkeypatch.setattr(admit, "host_is_locked", lambda root, host: False)
    switches = CardSwitches(
        config, _capacity(config), card_mib={SWAP_HOST: {0: CARD_MIB}}
    )

    lines, slept = wake_making_room(switches, RAM, ())

    assert slept is None
    assert lines == [
        f"wake {RAM}: failed: the live fleet does not hold {SWAP_HOST} locked"
    ]
