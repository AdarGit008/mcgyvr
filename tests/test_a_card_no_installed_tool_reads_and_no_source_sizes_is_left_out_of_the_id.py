"""A card no installed tool reads and no source sizes is left out of the rig id.

Beside the cards a machine's tools read, sysfs may show display adapters that
no card tool installed there reads and whose memory size it does not publish: a
management adapter, an integrated one, a virtual display. Such a card is listed
in the reading with its size unread and named in its ``unsized`` list, and the
rig id (:func:`mcgyvr.fleet.ids.rig_id`) leaves it out: the id of a card beside
it is the id of that card alone, and a machine whose only card is such an
adapter gets the id of a machine with no card. A card of a vendor whose tool is
installed, and a card whose size file is there but cannot be taken, keep the
refusal. A display entry that gives no PCI vendor id is named as one without a
vendor id, and, since no tool reads it, is left out when it publishes no size.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.machine_shapes import shapes
from tests.machinereader import (
    MIB,
    Staged,
    SysfsCard,
    expected_unsized,
    machine_reading,
    reading,
    run,
    unread,
)

CARD_LINE = b"0, 7919, 0, 7919, Example Card V\n"
TOOL_CARD = SysfsCard(number=0, vendor="0x10de", device="0x00aa")


def _read(staged: Staged, where: Path) -> dict[str, Any]:
    ran = run(staged, where)
    assert ran.returncode == 0, ran.stderr
    assert ran.unexpected == (), ran.unexpected
    return reading(ran.stdout)


def _rig_id(document: dict[str, Any]) -> str:
    from mcgyvr.fleet import ids

    return ids.rig_id(document)


def _keys(document: dict[str, Any]) -> list[str]:
    return [f"card.{c['vendor']}.{c['index']}" for c in document["cards"]]


def _with_tool(*sysfs: SysfsCard) -> Staged:
    return Staged(first_tool=CARD_LINE, sysfs=(TOOL_CARD, *sysfs))


@pytest.mark.parametrize(
    ("pci", "vendor"),
    [("0xfff0", "pci-0xfff0"), ("0x8086", "intel")],
    ids=["unassigned-vendor", "a-vendor-with-no-tool-here"],
)
def test_an_adapter_beside_a_card_its_tool_reads_leaves_the_id_of_that_card(
    pci: str, vendor: str, tmp_path: Path
) -> None:
    adapter = SysfsCard(number=1, vendor=pci, device="0x00bb")
    both = _read(_with_tool(adapter), tmp_path / "both")
    alone = _read(_with_tool(), tmp_path / "alone")
    key = f"card.{vendor}.1"
    assert key in _keys(both)
    assert both["unsized"] == [key]
    assert _rig_id(both) == _rig_id(alone)


def test_a_lone_adapter_gives_the_id_of_a_machine_with_no_card(
    tmp_path: Path,
) -> None:
    """The id then covers the machine id and no card, and the reading says so."""
    adapter = SysfsCard(number=0, vendor="0xfff0", device="0x00bb")
    lone = _read(Staged(sysfs=(adapter,)), tmp_path / "lone")
    none = _read(Staged(), tmp_path / "none")
    assert _keys(lone) == ["card.pci-0xfff0.0"]
    assert lone["unsized"] == ["card.pci-0xfff0.0"]
    assert none["cards"] == []
    assert _rig_id(lone) == _rig_id(none)


def test_the_size_reason_of_an_adapter_names_no_tool_that_may_read_it(
    tmp_path: Path,
) -> None:
    adapter = SysfsCard(number=1, vendor="0xfff0", device="0x00bb")
    why = unread(_read(_with_tool(adapter), tmp_path))["card.pci-0xfff0.1.total"]
    assert "no card tool installed here reads its vendor" in why
    assert "may read it" not in why


def test_a_card_whose_vendors_tool_is_installed_and_fails_keeps_the_refusal(
    tmp_path: Path,
) -> None:
    staged = Staged(first_tool=b"", first_tool_exit=3, sysfs=(TOOL_CARD,))
    document = _read(staged, tmp_path)
    assert _keys(document) == ["card.nvidia.0"]
    assert document["unsized"] == []
    with pytest.raises(ValueError, match=r"card\.nvidia\.0\.total"):
        _rig_id(document)


@pytest.mark.parametrize(
    "raw",
    [{"mem_info_vram_total": b"lots\n"}, {"mem_info_vram_total": b"1" * 5000}],
    ids=["not-a-number", "a-line-too-long"],
)
def test_a_size_file_that_is_there_but_not_taken_keeps_the_refusal(
    raw: dict[str, bytes], tmp_path: Path
) -> None:
    adapter = SysfsCard(number=1, vendor="0xfff0", device="0x00bb", raw=raw)
    document = _read(_with_tool(adapter), tmp_path)
    assert document["unsized"] == []
    with pytest.raises(ValueError, match=r"card\.pci-0xfff0\.1\.total"):
        _rig_id(document)


@pytest.mark.parametrize(
    "raw",
    [{}, {"vendor": b"\n"}, {"vendor": b"not an id\n"}],
    ids=["no-vendor-file", "an-empty-one", "one-without-an-id"],
)
def test_a_display_entry_with_no_vendor_id_is_named_as_one_and_left_out(
    raw: dict[str, bytes], tmp_path: Path
) -> None:
    entry = SysfsCard(number=2, vendor=None, device="0x00cc", raw=raw)
    document = _read(_with_tool(entry), tmp_path / "with")
    alone = _read(_with_tool(), tmp_path / "alone")
    assert "card.unknown.2" in _keys(document)
    assert document["unsized"] == ["card.unknown.2"]
    named = unread(document)
    assert "no PCI vendor id" in named["card.unknown.2.vendor"]
    assert not [f for f in named if "pci" in f]
    assert _rig_id(document) == _rig_id(alone)


def test_a_name_file_that_is_there_but_not_readable_falls_back_to_the_pci_name(
    tmp_path: Path,
) -> None:
    """A card whose name file is there but not readable keeps its id by the
    name the PCI ids give.
    """
    card = SysfsCard(
        number=0,
        vendor="0x1002",
        device="0x00aa",
        product_name_dir=True,
        vram_total_bytes=8192 * MIB,
        vram_used_bytes=0,
    )
    document = _read(Staged(sysfs=(card,)), tmp_path)
    (read,) = document["cards"]
    assert read["name"] == "PCI 0x1002:0x00aa"
    assert "card.amd.0.name" not in unread(document)
    assert _rig_id(document).startswith("rig-")


def test_every_invented_machine_names_exactly_its_unsized_cards(
    tmp_path: Path,
) -> None:
    for number, m in enumerate(shapes()):
        document = machine_reading(m, tmp_path / str(number))
        assert tuple(document["unsized"]) == expected_unsized(m), m.label
