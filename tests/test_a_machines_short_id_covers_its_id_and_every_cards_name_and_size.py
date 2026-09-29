"""A machine's short id covers its machine id and every card's name and size.

The short id is a digest, under its own identity prefix, over the machine id
and the list of every card's name and total memory. It changes when any of
those change, on any card, and only then: free and used memory, the processes
on a card, the host name and the containers do not move it. A reading that
could not read one of the covered fields gets no short id, and the refusal
names the field.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.machine_shapes import shape, shapes
from tests.machinereader import machine_read_text, replace, run, stage

if TYPE_CHECKING:
    from mcgyvr.fleet.machine import Reading


def _reading(label: str, where: Path) -> Reading:
    from mcgyvr.fleet import machine as reader

    return reader.parse(machine_read_text(shape(label), where))


def test_the_short_id_has_its_own_prefix_among_the_identity_prefixes() -> None:
    from mcgyvr.fleet import ids, machine

    assert machine.SHORT_ID_PREFIX in ids.IDENTITY_PREFIXES
    assert machine.SHORT_ID_PREFIX not in ids._RETIRED_PREFIXES


def test_every_readable_machine_gets_a_short_id_under_that_prefix(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine

    named = {}
    for number, m in enumerate(shapes()):
        reading = machine.parse(machine_read_text(m, tmp_path / str(number)))
        covered_unread = any(
            c.name is None or c.total_mib is None for c in reading.cards
        )
        if covered_unread:
            continue
        named[m.label] = machine.short_id(reading)
    assert named
    assert all(i.startswith(machine.SHORT_ID_PREFIX) for i in named.values())
    assert len(set(named.values())) == len(named)


def test_the_short_id_moves_with_any_cards_name_or_size_and_the_machine_id(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine

    reading = _reading("several-sizes", tmp_path)
    before = machine.short_id(reading)
    for place in range(len(reading.cards)):
        for change in ({"name": "Example Card Z"}, {"total_mib": 1}):
            cards = list(reading.cards)
            cards[place] = dataclasses.replace(cards[place], **change)
            moved = dataclasses.replace(reading, cards=tuple(cards))
            assert machine.short_id(moved) != before, (place, change)
    other = dataclasses.replace(reading, machine_id="f" * 16)
    assert machine.short_id(other) != before
    swapped = dataclasses.replace(reading, cards=reading.cards[::-1])
    assert machine.short_id(swapped) != before
    fewer = dataclasses.replace(reading, cards=reading.cards[:-1])
    assert machine.short_id(fewer) != before


def test_the_short_id_ignores_what_is_not_the_machine(tmp_path: Path) -> None:
    from mcgyvr.fleet import machine

    reading = _reading("busy-beside-free", tmp_path)
    before = machine.short_id(reading)
    idle = tuple(
        dataclasses.replace(c, used_mib=0, free_mib=c.total_mib, holders=())
        for c in reading.cards
    )
    elsewhere = dataclasses.replace(
        reading,
        cards=idle,
        host="box-3.example",
        containers=(),
        machine_id_from="hostname",
    )
    assert machine.short_id(elsewhere) == before


def test_the_same_cards_on_two_machines_get_two_short_ids(tmp_path: Path) -> None:
    from mcgyvr.fleet import machine

    here = _reading("same-cards-here", tmp_path / "here")
    there = _reading("same-cards-there", tmp_path / "there")
    assert machine.short_id(here) != machine.short_id(there)


@pytest.mark.parametrize(
    ("label", "named"),
    [
        ("unreadable-size", "card.nvidia.1.total"),
        ("no-reader", "card.nvidia.0.total"),
    ],
)
def test_a_reading_missing_a_covered_field_gets_no_short_id_and_names_it(
    label: str, named: str, tmp_path: Path
) -> None:
    from mcgyvr.fleet import machine

    reading = _reading(label, tmp_path)
    with pytest.raises(ValueError, match=named.replace(".", r"\.")):
        machine.short_id(reading)


def test_a_card_tool_that_failed_gets_no_short_id(tmp_path: Path) -> None:
    from mcgyvr.fleet import machine

    staged = replace(stage(shape("one-card")), first_tool=b"", first_tool_exit=3)
    reading = machine.parse(run(staged, tmp_path).stdout)
    with pytest.raises(ValueError, match=r"cards\.nvidia-smi"):
        machine.short_id(reading)


def test_a_reading_without_a_machine_id_gets_no_short_id() -> None:
    from mcgyvr.fleet import machine

    reading = machine.parse("host=box-4.example\ncards=none\n")
    with pytest.raises(ValueError, match="machine_id"):
        machine.short_id(reading)
