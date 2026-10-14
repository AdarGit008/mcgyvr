"""Every card of a machine is read, each with its own figures, not only the first.

Over every invented machine, the one reader's document
(:mod:`mcgyvr.serving.rigscan`) holds each card the machine's tools show, and
from sysfs each card of a vendor no answering tool covered, keyed by its vendor
and index, with its name, total, used and free memory; no card is listed twice,
and when sysfs shows more cards of a vendor than its tool printed, that tool's
list is named unread, and the machine gets no rig id. The reading holds figures
per card only: it has no field that sums the cards or picks one of them, so a
machine of several cards is never read as its first.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.machine_shapes import Shape, shapes
from tests.machinereader import (
    MIB,
    Staged,
    SysfsCard,
    cards,
    expected_cards,
    expected_sources,
    machine_reading,
    reading,
    run,
    unread,
)


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_every_card_is_read_with_its_own_figures(
    machine: Shape, tmp_path: Path
) -> None:
    document = machine_reading(machine, tmp_path)
    assert cards(document) == expected_cards(machine)
    assert document["card_sources"] == list(expected_sources(machine))


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


def test_the_reading_holds_figures_per_card_and_none_for_the_machine(
    tmp_path: Path,
) -> None:
    """The fields later readers rely on are there; a field may be added. No
    field of the reading or of a card sums the cards or picks one of them."""
    document = reading(
        run(Staged(first_tool=b"0, 7919, 0, 7919, Example Card P\n"), tmp_path).stdout
    )
    assert {"machine", "cards", "card_sources", "unsized", "unread"} <= set(document)
    assert {"id", "id_from", "host"} <= set(document["machine"])
    (card,) = document["cards"]
    assert {"vendor", "index", "name", "total_mib", "used_mib", "free_mib"} <= set(card)
    for fields in (document, card):
        summed = [n for n in fields if "sum" in n or "first" in n]
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
    from mcgyvr.fleet import ids

    staged = Staged(
        first_tool=FIRST_CARD,
        sysfs=(
            SysfsCard(number=0, vendor="0x10de", device="0x1b1b"),
            _other_vendor_in_sysfs(1),
        ),
    )
    document = reading(run(staged, tmp_path).stdout)
    assert [card[:4] for card in cards(document)] == [
        ("amd", 1, "Example Card Q", 5003),
        ("nvidia", 0, "Example Card P", 7919),
    ]
    assert document["card_sources"] == ["nvidia-smi", "sysfs"]
    assert ids.rig_id(document).startswith("rig-")


def test_sysfs_showing_more_cards_of_a_vendor_than_its_tool_names_the_tool(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import ids

    staged = Staged(
        first_tool=FIRST_CARD,
        sysfs=(
            SysfsCard(number=0, vendor="0x10de", device="0x1b1b"),
            SysfsCard(number=1, vendor="0x10de", device="0x1b1b"),
        ),
    )
    document = reading(run(staged, tmp_path).stdout)
    assert [card[:2] for card in cards(document)] == [("nvidia", 0)]
    why = unread(document)["cards.nvidia-smi"]
    assert "2" in why and "1" in why
    with pytest.raises(ValueError, match=r"cards\.nvidia-smi"):
        ids.rig_id(document)
