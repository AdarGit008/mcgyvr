"""A unit that spans cards or rigs names each card, and a wrong naming is refused.

A unit says which cards it occupies in its free-form ``launch`` block, as
``shards``: one entry per card, naming the rig, the card's index there and the
room that card needs. The first shard is the head's, so it is on the unit's own
rig. The result is a span: the head, the rigs spanned in order, and the cards of
each. A unit that names no shards is not a span and is what it always was. A
declaration that cannot be read is refused by unit and shard, never defaulted:

* shards that are not a list of mappings;
* a shard that names no rig, or whose card index is not a whole number from 0;
* a first shard that is not on the unit's own rig;
* one card named twice;
* a shard on a rig the fleet does not list.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.fleet import lock, spans
from mcgyvr.fleet.layout import FleetError
from tests import span_fleet as sf


def test_a_unit_with_shards_is_a_span_that_says_its_head_rigs_and_cards() -> None:
    found = spans.spans(sf.fleet())
    assert set(found) == {sf.BIG, sf.REMOTE}, "a unit with no shards is no span"
    big = found[sf.BIG]
    assert big.head == sf.A
    assert big.rigs == (sf.A, sf.B)
    assert big.cards == {sf.A: (0, 1), sf.B: (0,)}
    assert big.room == {(sf.A, 0): 3000, (sf.A, 1): 2500, (sf.B, 0): 2000}


def test_a_head_that_sorts_after_its_worker_still_comes_first() -> None:
    remote = spans.spans(sf.fleet())[sf.REMOTE]
    assert remote.head == sf.B
    assert remote.rigs == (sf.B, sf.A), "the head is first, not the first by name"
    assert remote.workers == (sf.A,)


def test_a_rig_is_listed_once_in_the_order_it_was_first_named() -> None:
    fleet = sf.fleet()
    fleet["units"][sf.BIG]["launch"]["shards"] = [
        {"rig": sf.A, "gpu": 0},
        {"rig": sf.B, "gpu": 0},
        {"rig": sf.A, "gpu": 1},
    ]
    big = spans.spans(fleet)[sf.BIG]
    assert big.rigs == (sf.A, sf.B)
    assert big.cards[sf.A] == (0, 1)
    assert big.room[(sf.A, 0)] is None, "a room nobody stated is not made up"


def test_a_one_entry_list_pins_a_single_card_unit() -> None:
    fleet = sf.with_small_on_a_card(sf.fleet(), gpu=1)
    small = spans.spans(fleet)[sf.SMALL]
    assert small.rigs == (sf.A,)
    assert small.cards == {sf.A: (1,)}


def _edit(change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    fleet = copy.deepcopy(sf.fleet())
    change(fleet)
    return fleet


def _shards(fleet: dict[str, Any]) -> list[Any]:
    shards: list[Any] = fleet["units"][sf.BIG]["launch"]["shards"]
    return shards


REFUSED: list[tuple[str, Callable[[dict[str, Any]], None], str]] = [
    (
        "shards that are not a list",
        lambda f: f["units"][sf.BIG]["launch"].update(shards={"rig": sf.A, "gpu": 0}),
        "expected a list of shards",
    ),
    (
        "an empty list of shards",
        lambda f: f["units"][sf.BIG]["launch"].update(shards=[]),
        "expected a list of shards",
    ),
    (
        "a shard that is not a mapping",
        lambda f: _shards(f).__setitem__(1, "card 1"),
        "shards[1]: a shard is a mapping",
    ),
    (
        "a shard with no rig",
        lambda f: _shards(f)[2].pop("rig"),
        "shards[2]: names no rig",
    ),
    (
        "a shard with no card index",
        lambda f: _shards(f)[1].pop("gpu"),
        "shards[1]: gpu is None",
    ),
    (
        "a negative card index",
        lambda f: _shards(f)[1].update(gpu=-1),
        "gpu is -1",
    ),
    (
        "a card index that is text",
        lambda f: _shards(f)[1].update(gpu="1"),
        "gpu is '1'",
    ),
    (
        "a card index that is true",
        lambda f: _shards(f)[1].update(gpu=True),
        "gpu is True",
    ),
    (
        "a room that is not above 0",
        lambda f: _shards(f)[0].update(room_mib=0),
        "room_mib is 0",
    ),
    (
        "a shard key nobody reads",
        lambda f: _shards(f)[0].update(split="layer"),
        "unknown key 'split'",
    ),
    (
        "a first shard that is not the head's",
        lambda f: _shards(f).reverse(),
        "the first shard is on box-b.example",
    ),
    (
        "one card named twice",
        lambda f: _shards(f).append({"rig": sf.A, "gpu": 1}),
        "card 1 of box-a.example is named twice",
    ),
    (
        "a shard on a rig fleet.yaml does not list",
        lambda f: _shards(f)[2].update(rig="box-c.example"),
        "box-c.example, which fleet.yaml does not list",
    ),
    (
        "shards on a unit that has no rig",
        lambda f: f["units"][sf.BIG].pop("rig"),
        "declares shards but no `rig`",
    ),
]


@pytest.mark.parametrize(
    ("change", "said"),
    [(change, said) for _label, change, said in REFUSED],
    ids=[label for label, _change, _said in REFUSED],
)
def test_a_wrong_naming_is_refused_by_unit_and_shard(
    change: Callable[[dict[str, Any]], None], said: str
) -> None:
    fleet = _edit(change)
    with pytest.raises(FleetError) as refused:
        spans.spans(fleet)
    assert isinstance(refused.value, spans.SpanError)
    assert sf.BIG in str(refused.value) and said in str(refused.value), refused.value


def test_the_lock_refuses_a_wrong_naming_whether_or_not_a_fleet_places_the_unit(
    tmp_path: Path,
) -> None:
    fleet = _edit(lambda f: _shards(f)[2].update(rig="box-c.example"))
    with pytest.raises(lock.LockRefusedError, match=r"box-c\.example"):
        lock.write(tmp_path, fleet, sf.evidence(), tolerances=sf.TOLERANCES)
    assert not any(tmp_path.iterdir()), "nothing is written when it refuses"
