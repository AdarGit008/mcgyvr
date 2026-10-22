"""A wake on a shared card makes room first: the smaller unit sleeps first.

Two vLLM units co-resident on one card each run as their own process, and each
can sleep at level 2 alone — the process stays, its weights and KV cache leave
the card. Where the two cannot both be awake on the card, waking the bigger one
means putting the smaller one to sleep first, and giving the room back when the
bigger one sleeps again.

Whether they fit is arithmetic on facts mcgyvr already holds: each unit's
``room_mib`` from the config, the card each unit is on from the launch spec
that starts it, and that card's memory from the host's recorded scan, which
``emit`` sizes against. On a host with several cards only the units on the
waking unit's card are its neighbours. Where a figure is missing, or the card
a unit is on cannot be told, there is no answer, no room is made, and the
switches say why. Every number and shape here is invented.

On such a card a sleep and a wake act on one unit (``serve sleep|wake --unit``),
the card's other units are left as they are, and the record of who is resting
is kept per unit.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import Config, parse
from mcgyvr.ladder_manager import wake_making_room
from tests.doors import (  # noqa: F401 - fixtures
    FAST,
    FAST_HOST,
    LARGE,
    LARGE_CONTAINER,
    SHARED_HOST,
    SMALL,
    SMALL_CONTAINER,
    a_clean_home,
    ladder_text,
    reservation,
    write_spec,
)


def door(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The door, recorded as ``<verb>`` or ``<verb> <unit>``; every run works."""
    import mcgyvr.wake as wake

    log: list[str] = []

    def spawn(argv: list[str], **_: Any) -> int:
        said = argv[argv.index("serve") + 1]
        if "--unit" in argv:
            said += " " + argv[argv.index("--unit") + 1]
        log.append(said)
        return 0

    monkeypatch.setattr(wake, "spawn_door", spawn)
    return log


def switches(
    config: Config,
    card_mib: int | None = 12000,
    *,
    sizes: dict[int, int] | None = None,
) -> Any:
    """The card switches, with the shared host's card sizes by card index.

    ``card_mib`` is a one-card host's one card; ``sizes`` states every card.
    """
    from mcgyvr.capacity import Capacity
    from mcgyvr.pressure import Gauge
    from mcgyvr.wake import CardSwitches

    if sizes is None:
        sizes = {} if card_mib is None else {0: card_mib}
    rooms = {SHARED_HOST: sizes} if sizes else {}
    return CardSwitches(config, Capacity.of(config, gauge=Gauge()), card_mib=rooms)


# --- how much room ---------------------------------------------------------------


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return a_clean_home(tmp_path, monkeypatch)


def test_waking_the_larger_unit_needs_the_smaller_ones_room(
    tmp_path: Path, home: Path
) -> None:
    config = parse(ladder_text(write_spec(tmp_path)))

    assert switches(config).room_for(LARGE) == (SMALL,)


def test_units_that_fit_the_card_together_need_no_room(
    tmp_path: Path, home: Path
) -> None:
    config = parse(ladder_text(write_spec(tmp_path)))

    assert switches(config, card_mib=16000).room_for(LARGE) == ()


@pytest.mark.parametrize(
    "missing",
    ["card", "small_mib"],
    ids=["no-card-size", "no-room-mib"],
)
def test_without_the_numbers_there_is_no_room_to_make(
    tmp_path: Path, home: Path, missing: str
) -> None:
    specs = write_spec(tmp_path)
    if missing == "small_mib":
        config = parse(ladder_text(specs, small_mib=None))
    else:
        config = parse(ladder_text(specs))

    card = None if missing == "card" else 12000
    assert switches(config, card_mib=card).room_for(LARGE) == ()


def test_a_shared_llamacpp_card_makes_room_the_same_way(
    tmp_path: Path, home: Path
) -> None:
    """A llama.cpp unit's sleep is a stop of its container, so it swaps too."""
    config = parse(ladder_text(write_spec(tmp_path), engine="llama.cpp"))

    assert switches(config).room_for(LARGE) == (SMALL,)
    assert switches(config).card_of(LARGE) == (LARGE,)


def test_a_shared_vllm_card_switches_one_unit_at_a_time(
    tmp_path: Path, home: Path
) -> None:
    config = parse(ladder_text(write_spec(tmp_path)))

    assert switches(config).card_of(LARGE) == (LARGE,)
    assert switches(config).card_of(SMALL) == (SMALL,)


# --- several cards on one host ---------------------------------------------------


def test_on_a_host_of_several_cards_room_is_made_on_the_waking_units_card(
    tmp_path: Path, home: Path
) -> None:
    config = parse(ladder_text(write_spec(tmp_path, small_on=["1"], large_on=["1"])))

    card = switches(config, sizes={0: 24000, 1: 12000})

    assert card.room_for(LARGE) == (SMALL,), (
        "both units are on the 12000 MiB card, and 4000 + 9000 does not fit it"
    )
    assert card.why_no_room(LARGE) is None


def test_a_unit_on_another_card_holds_no_room_on_this_one(
    tmp_path: Path, home: Path
) -> None:
    config = parse(ladder_text(write_spec(tmp_path, small_on=["0"], large_on=["1"])))

    card = switches(config, sizes={0: 12000, 1: 9000})

    assert card.room_for(LARGE) == (), (
        "the small unit is on the other card; sleeping it frees nothing here"
    )
    assert card.why_no_room(LARGE) is None


def test_the_card_of_a_one_card_host_needs_no_reservation_in_the_spec(
    tmp_path: Path, home: Path
) -> None:
    config = parse(ladder_text(write_spec(tmp_path)))

    assert switches(config, sizes={0: 12000}).room_for(LARGE) == (SMALL,)


@pytest.mark.parametrize(
    ("small_on", "large_on", "sizes", "said"),
    [
        (None, None, {0: 12000, 1: 12000}, "which card"),
        (["0"], ["0", "1"], {0: 12000, 1: 12000}, "more than one card"),
        (["0"], ["GPU-not-an-index"], {0: 12000, 1: 12000}, "which card"),
        (["0"], ["2"], {0: 12000, 1: 12000}, "no recorded scan"),
        (["0"], ["0"], {}, "no rig file answers for"),
    ],
    ids=[
        "no-reservation",
        "spans-two-cards",
        "not-an-index",
        "unscanned-card",
        "no-scan",
    ],
)
def test_where_the_card_cannot_be_told_no_room_is_made_and_why_is_said(
    tmp_path: Path,
    home: Path,
    small_on: list[str] | None,
    large_on: list[str] | None,
    sizes: dict[int, int],
    said: str,
) -> None:
    config = parse(
        ladder_text(write_spec(tmp_path, small_on=small_on, large_on=large_on))
    )

    card = switches(config, sizes=sizes)

    assert card.room_for(LARGE) == ()
    why = card.why_no_room(LARGE)
    assert why is not None and said in why, why


# --- one unit at a time -------------------------------------------------------------


def test_a_sleep_on_a_shared_card_sleeps_that_unit_alone(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = parse(ladder_text(write_spec(tmp_path)))
    doors = door(monkeypatch)

    assert switches(config).sleep(SMALL) is True
    assert doors == [f"sleep {SMALL_CONTAINER}"]


def test_a_resting_unit_is_woken_alone_and_its_neighbour_is_not(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = parse(ladder_text(write_spec(tmp_path)))
    doors = door(monkeypatch)
    card = switches(config)

    assert card.sleep(LARGE) is True
    assert card.wake(LARGE) is True
    assert doors == [f"sleep {LARGE_CONTAINER}", f"wake {LARGE_CONTAINER}"]


def test_resting_is_kept_per_unit_and_read_per_unit(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.serving import host_of, port_of
    from mcgyvr.wake import resting

    config = parse(ladder_text(write_spec(tmp_path)))
    door(monkeypatch)

    def rests(unit: str) -> bool:
        address = config.units[unit].address
        return resting(host_of(address), port_of(address))

    assert switches(config).sleep(SMALL) is True
    assert rests(SMALL) is True
    assert rests(LARGE) is False, "the neighbour was not slept"


# --- the room is made first --------------------------------------------------------


def test_waking_the_larger_unit_sleeps_the_smaller_one_first(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = parse(ladder_text(write_spec(tmp_path)))
    doors = door(monkeypatch)
    card = switches(config)
    assert card.sleep(LARGE) is True  # the larger unit rests, as it would

    wake_making_room(card, LARGE, card.room_for(LARGE))

    assert doors == [
        f"sleep {LARGE_CONTAINER}",
        f"sleep {SMALL_CONTAINER}",
        f"wake {LARGE_CONTAINER}",
    ]


# --- a unit split across machines ------------------------------------------------
