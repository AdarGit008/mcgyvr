"""A card of another vendor than the first tool's is read by its name and size.

The reader asks the first vendor's tool, then the second vendor's, and falls
back to sysfs only when neither tool gave a card. A card the second vendor's
tool reads, or one sysfs publishes a size for, is in the reading with its name
and its total memory. A card sysfs publishes no name or size for is still in
the reading, named by its bus ids, and its size is named as unread.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.machine_shapes import Shape, shapes
from tests.machinereader import (
    MIB,
    Staged,
    SysfsCard,
    expected_cards,
    machine_read_text,
    replace,
    run,
    stage,
)

OTHER = [m for m in shapes() if any(c.vendor == "vendor-b" for c in m.cards)]


@pytest.mark.parametrize("machine", OTHER, ids=lambda m: m.label)
def test_every_card_of_the_other_vendor_is_read_by_name_and_size(
    machine: Shape, tmp_path: Path
) -> None:
    from mcgyvr.fleet import machine as reader

    reading = reader.parse(machine_read_text(machine, tmp_path))
    wanted = [c for c in expected_cards(machine) if c[0] == "amd"]
    assert wanted
    got = [
        (c.vendor, c.index, c.name, c.total_mib)
        for c in reading.cards
        if c.vendor == "amd"
    ]
    assert got == [c[:4] for c in wanted]
    assert all(name for _, _, name, _ in got)
    assert all(total is not None for *_, total in got)


def test_a_machine_of_two_vendors_is_read_by_both_tools(tmp_path: Path) -> None:
    from mcgyvr.fleet import machine as reader

    mixed = next(m for m in shapes() if m.label == "mixed-vendors")
    reading = reader.parse(machine_read_text(mixed, tmp_path))
    assert reading.card_sources == ("nvidia-smi", "rocm-smi")
    assert {c.vendor for c in reading.cards} == {"nvidia", "amd"}


def test_the_second_tools_keys_are_read_whatever_their_case(tmp_path: Path) -> None:
    from mcgyvr.fleet import machine as reader

    text = json.dumps(
        {
            "card0": {
                "CARD SERIES": "Example Card Q",
                "vram total memory (b)": str(12 * 1024 * MIB),
                "VRAM TOTAL USED MEMORY (B)": str(3 * MIB),
            }
        }
    ).encode()
    reading = reader.parse(run(Staged(second_tool=text), tmp_path).stdout)
    (card,) = reading.cards
    assert (card.name, card.total_mib, card.used_mib, card.free_mib) == (
        "Example Card Q",
        12 * 1024,
        3,
        12 * 1024 - 3,
    )


def test_a_card_sysfs_names_nothing_for_is_named_by_its_bus_ids(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine as reader

    staged = Staged(sysfs=(SysfsCard(number=0, vendor="0x1d0f", device="0x00aa"),))
    reading = reader.parse(run(staged, tmp_path).stdout)
    (card,) = reading.cards
    assert (card.vendor, card.index, card.name, card.total_mib) == (
        "pci-0x1d0f",
        0,
        "PCI 0x1d0f:0x00aa",
        None,
    )
    assert reading.card_sources == ("sysfs",)
    unread = {u.field: u.why for u in reading.unread}
    assert "card.pci-0x1d0f.0.total" in unread
    assert "sysfs" in unread["card.pci-0x1d0f.0.total"]


def test_the_second_tool_without_python_is_named_unread(tmp_path: Path) -> None:
    from mcgyvr.fleet import machine as reader

    machine = next(m for m in shapes() if m.label == "other-vendor")
    staged = replace(stage(machine), python=False)
    reading = reader.parse(run(staged, tmp_path).stdout)
    unread = {u.field: u.why for u in reading.unread}
    assert "python3" in unread["cards.rocm-smi"]
    # With no card from any tool, sysfs is read.
    assert reading.card_sources == ("sysfs",)
