"""A card no installed tool reads and no source sizes is left out of the short id.

Beside the cards a machine's tools read, sysfs may show display adapters that
no card tool installed there reads and whose memory size it does not publish:
a management adapter, an integrated one, a virtual display. Such a card is
listed in the reading with its size unread and named in ``Reading.unsized``,
and the short id leaves it out: the id of a card beside it is the id of that
card alone, and a machine whose only card is such an adapter gets the id of a
machine with no card. A card of a vendor whose tool is installed, and a card
whose size file is there but cannot be taken, keep the refusal. A display
entry that gives no PCI vendor id is such an adapter too, and is named as one
without a vendor id.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.machine_shapes import shapes
from tests.machinereader import (
    MIB,
    Staged,
    SysfsCard,
    expected_unsized,
    machine_read_text,
    run,
)

if TYPE_CHECKING:
    from mcgyvr.fleet.machine import Reading

CARD_LINE = b"0, 7919, 0, 7919, Example Card V\n"
TOOL_CARD = SysfsCard(number=0, vendor="0x10de", device="0x00aa")


def _read(staged: Staged, where: Path) -> Reading:
    from mcgyvr.fleet import machine

    ran = run(staged, where)
    assert ran.returncode == 0, ran.stderr
    assert ran.unexpected == (), ran.unexpected
    return machine.parse(ran.stdout)


def _with_tool(*sysfs: SysfsCard) -> Staged:
    return Staged(
        first_tool=CARD_LINE,
        first_tool_processes={0: (b"", 0)},
        sysfs=(TOOL_CARD, *sysfs),
    )


@pytest.mark.parametrize(
    ("pci", "vendor"),
    [("0xfff0", "pci-0xfff0"), ("0x8086", "intel")],
    ids=["unassigned-vendor", "a-vendor-with-no-tool-here"],
)
def test_an_adapter_beside_a_card_its_tool_reads_leaves_the_id_of_that_card(
    pci: str, vendor: str, tmp_path: Path
) -> None:
    from mcgyvr.fleet import machine

    adapter = SysfsCard(number=1, vendor=pci, device="0x00bb")
    both = _read(_with_tool(adapter), tmp_path / "both")
    alone = _read(_with_tool(), tmp_path / "alone")
    key = f"card.{vendor}.1"
    assert key in {c.key for c in both.cards}
    assert both.unsized == (key,)
    assert machine.short_id(both) == machine.short_id(alone)


def test_a_lone_adapter_gives_the_id_of_a_machine_with_no_card(
    tmp_path: Path,
) -> None:
    """The id then covers the machine id and no card, and the reading says so."""
    from mcgyvr.fleet import machine

    adapter = SysfsCard(number=0, vendor="0xfff0", device="0x00bb")
    lone = _read(Staged(sysfs=(adapter,)), tmp_path / "lone")
    none = _read(Staged(), tmp_path / "none")
    assert [c.key for c in lone.cards] == ["card.pci-0xfff0.0"]
    assert lone.unsized == ("card.pci-0xfff0.0",)
    assert none.cards == ()
    assert machine.short_id(lone) == machine.short_id(none)


def test_the_size_reason_of_an_adapter_names_no_tool_that_may_read_it(
    tmp_path: Path,
) -> None:
    adapter = SysfsCard(number=1, vendor="0xfff0", device="0x00bb")
    reading = _read(_with_tool(adapter), tmp_path)
    why = {u.field: u.why for u in reading.unread}["card.pci-0xfff0.1.total"]
    assert "no card tool installed here reads its vendor" in why
    assert "may read it" not in why


def test_a_card_whose_vendors_tool_is_installed_and_fails_keeps_the_refusal(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine

    staged = Staged(first_tool=b"", first_tool_exit=3, sysfs=(TOOL_CARD,))
    reading = _read(staged, tmp_path)
    assert [c.key for c in reading.cards] == ["card.nvidia.0"]
    assert reading.unsized == ()
    with pytest.raises(ValueError, match=r"card\.nvidia\.0\.total"):
        machine.short_id(reading)


@pytest.mark.parametrize(
    "raw",
    [{"mem_info_vram_total": b"lots\n"}, {"mem_info_vram_total": b"1" * 5000}],
    ids=["not-a-number", "a-line-too-long"],
)
def test_a_size_file_that_is_there_but_not_taken_keeps_the_refusal(
    raw: dict[str, bytes], tmp_path: Path
) -> None:
    from mcgyvr.fleet import machine

    adapter = SysfsCard(number=1, vendor="0xfff0", device="0x00bb", raw=raw)
    reading = _read(_with_tool(adapter), tmp_path)
    assert reading.unsized == ()
    with pytest.raises(ValueError, match=r"card\.pci-0xfff0\.1\.total"):
        machine.short_id(reading)


@pytest.mark.parametrize(
    "raw",
    [{}, {"vendor": b"\n"}, {"vendor": b"not an id\n"}],
    ids=["no-vendor-file", "an-empty-one", "one-without-an-id"],
)
def test_a_display_entry_with_no_vendor_id_is_named_as_one_and_left_out(
    raw: dict[str, bytes], tmp_path: Path
) -> None:
    from mcgyvr.fleet import machine

    entry = SysfsCard(number=2, vendor=None, device="0x00cc", raw=raw)
    reading = _read(_with_tool(entry), tmp_path / "with")
    alone = _read(_with_tool(), tmp_path / "alone")
    assert "card.unknown.2" in {c.key for c in reading.cards}
    assert reading.unsized == ("card.unknown.2",)
    unread = {u.field: u.why for u in reading.unread}
    assert "no PCI vendor id" in unread["card.unknown.2.vendor"]
    assert not [f for f in unread if "pci" in f]
    assert machine.short_id(reading) == machine.short_id(alone)


def test_a_name_file_that_is_there_but_not_readable_falls_back_to_the_pci_name(
    tmp_path: Path,
) -> None:
    """A card whose name file is there but not readable keeps its id by the name the PCI ids give."""
    from mcgyvr.fleet import machine

    card = SysfsCard(
        number=0,
        vendor="0x1002",
        device="0x00aa",
        product_name_dir=True,
        vram_total_bytes=8192 * MIB,
        vram_used_bytes=0,
    )
    reading = _read(Staged(sysfs=(card,)), tmp_path)
    (read,) = reading.cards
    assert read.name == "PCI 0x1002:0x00aa"
    assert "card.amd.0.name" not in {u.field for u in reading.unread}
    assert machine.short_id(reading).startswith(machine.SHORT_ID_PREFIX)


def test_every_invented_machine_names_exactly_its_unsized_cards(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine

    for number, m in enumerate(shapes()):
        reading = machine.parse(machine_read_text(m, tmp_path / str(number)))
        assert reading.unsized == expected_unsized(m), m.label
