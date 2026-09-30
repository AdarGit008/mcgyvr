"""Every card of a machine is read, each with its own figures, not only the first.

Over every invented machine, the reading holds each card the machine's tools
show, and from sysfs each card of a vendor no answering tool covered, keyed by
its vendor and index, with its name, total, used and free memory and the
processes holding it; no card is listed twice, and when sysfs shows more cards
of a vendor than its tool printed, that tool's list is named unread. The
reading holds figures per card only: it has no field that sums the cards or
picks one of them.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from tests.machine_shapes import Shape, shapes
from tests.machinereader import (
    MIB,
    Staged,
    SysfsCard,
    expected_cards,
    expected_sources,
    machine_read_text,
    run,
)


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
    assert reading.card_sources == expected_sources(machine)


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


def _fields(kind: type) -> list[str]:
    return [f.name for f in dataclasses.fields(kind)]


def test_the_reading_holds_figures_per_card_and_none_for_the_machine() -> None:
    """The fields later readers rely on are there; a field may be added."""
    from mcgyvr.fleet import machine as reader

    assert {
        "machine_id",
        "machine_id_from",
        "host",
        "card_sources",
        "cards",
        "containers",
        "unread",
    } <= set(_fields(reader.Reading))
    assert {
        "vendor",
        "index",
        "name",
        "total_mib",
        "used_mib",
        "free_mib",
        "holders",
    } <= set(_fields(reader.Card))
    assert {"pid", "name", "mib"} <= set(_fields(reader.Holder))
    assert {"name", "id", "project", "restarts"} <= set(_fields(reader.Container))
    assert {"field", "why"} <= set(_fields(reader.Unread))
    for kind in (reader.Reading, reader.Card):
        summed = [n for n in _fields(kind) if "sum" in n or "first" in n]
        assert not summed, summed


FIRST_CARD = b"0, 7919, 0, 7919, Example Card P\n"


def _other_vendor_in_sysfs(number: int, name: str = "Example Card Q") -> SysfsCard:
    return SysfsCard(
        number=number,
        vendor="0x1002",
        device="0x7a7a",
        product_name=name,
        vram_total_bytes=5003 * MIB,
        vram_used_bytes=0,
    )


def test_a_card_no_answering_tool_covers_is_read_from_sysfs_beside_the_tools(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine as reader

    staged = Staged(
        first_tool=FIRST_CARD,
        first_tool_processes={0: (b"", 0)},
        sysfs=(
            SysfsCard(number=0, vendor="0x10de", device="0x1b1b"),
            _other_vendor_in_sysfs(1),
        ),
    )
    reading = reader.parse(run(staged, tmp_path).stdout)
    assert [(c.vendor, c.index, c.name, c.total_mib) for c in reading.cards] == [
        ("amd", 1, "Example Card Q", 5003),
        ("nvidia", 0, "Example Card P", 7919),
    ]
    assert reading.card_sources == ("nvidia-smi", "sysfs")
    assert reader.short_id(reading).startswith(reader.SHORT_ID_PREFIX)


def test_sysfs_showing_more_cards_of_a_vendor_than_its_tool_names_the_tool(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine as reader

    staged = Staged(
        first_tool=FIRST_CARD,
        first_tool_processes={0: (b"", 0)},
        sysfs=(
            SysfsCard(number=0, vendor="0x10de", device="0x1b1b"),
            SysfsCard(number=1, vendor="0x10de", device="0x1b1b"),
        ),
    )
    reading = reader.parse(run(staged, tmp_path).stdout)
    assert [(c.vendor, c.index) for c in reading.cards] == [("nvidia", 0)]
    why = {u.field: u.why for u in reading.unread}["cards.nvidia-smi"]
    assert "2" in why and "1" in why
    with pytest.raises(ValueError, match=r"cards\.nvidia-smi"):
        reader.short_id(reading)
