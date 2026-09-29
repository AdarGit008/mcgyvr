"""Every card of a machine is read, each with its own figures, not only the first.

Over every invented machine, the reading holds each card the machine's tools
or sysfs show, keyed by its vendor and index, with its name, total, used and
free memory and the processes holding it. The reading holds figures per card
only: it has no field that sums the cards or picks one of them.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from tests.machine_shapes import Shape, shapes
from tests.machinereader import expected_cards, machine_read_text


def _as_expected(card: object) -> tuple[object, ...]:
    from mcgyvr.fleet.machine import Card

    assert isinstance(card, Card)
    holders = (
        None
        if card.holders is None
        else tuple((h.pid, h.name, h.mib) for h in card.holders)
    )
    return (
        card.vendor,
        card.index,
        card.name,
        card.total_mib,
        card.used_mib,
        card.free_mib,
        holders,
    )


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_every_card_is_read_with_its_own_figures(
    machine: Shape, tmp_path: Path
) -> None:
    from mcgyvr.fleet import machine as reader

    reading = reader.parse(machine_read_text(machine, tmp_path))
    assert [_as_expected(card) for card in reading.cards] == expected_cards(machine)


def test_a_machine_of_several_cards_reads_more_than_one() -> None:
    """The set of shapes holds machines whose later cards differ from the first,
    so the test above cannot pass by reading the first card only."""
    differing = [
        m
        for m in shapes()
        if len(expected_cards(m)) > 1
        and len({card[2:6] for card in expected_cards(m)}) > 1
    ]
    assert differing


def test_the_reading_holds_figures_per_card_and_none_for_the_machine() -> None:
    from mcgyvr.fleet import machine as reader

    assert [f.name for f in dataclasses.fields(reader.Reading)] == [
        "machine_id",
        "machine_id_from",
        "host",
        "card_sources",
        "cards",
        "containers",
        "unread",
    ]
    assert [f.name for f in dataclasses.fields(reader.Card)] == [
        "vendor",
        "index",
        "name",
        "total_mib",
        "used_mib",
        "free_mib",
        "holders",
    ]
    assert [f.name for f in dataclasses.fields(reader.Holder)] == [
        "pid",
        "name",
        "mib",
    ]
    assert [f.name for f in dataclasses.fields(reader.Container)] == [
        "name",
        "id",
        "project",
        "restarts",
    ]
    assert [f.name for f in dataclasses.fields(reader.Unread)] == ["field", "why"]
