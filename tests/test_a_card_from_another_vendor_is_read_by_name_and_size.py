"""A card of another vendor than the first tool's is read by its name and size.

The reader asks the first vendor's tool and the second vendor's, and takes
from sysfs the cards of any vendor no answering tool covered. A card the second
vendor's tool reads, or one sysfs publishes a size for, is in the reading with
its name and its total memory. A card sysfs publishes no name or size for is
still in the reading, named by its bus ids, and its size is named as unread.
The second tool's JSON is read by code the reader brings, never by code found
in the folder it runs in.
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
                "vram total memory (b)": str(11_111 * MIB),
                "VRAM TOTAL USED MEMORY (B)": str(3 * MIB),
            }
        }
    ).encode()
    reading = reader.parse(run(Staged(second_tool=text), tmp_path).stdout)
    (card,) = reading.cards
    assert (card.name, card.total_mib, card.used_mib, card.free_mib) == (
        "Example Card Q",
        11_111,
        3,
        11_111 - 3,
    )


def test_a_card_sysfs_names_nothing_for_is_named_by_its_bus_ids(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine as reader

    staged = Staged(sysfs=(SysfsCard(number=0, vendor="0xfff0", device="0x00aa"),))
    reading = reader.parse(run(staged, tmp_path).stdout)
    (card,) = reading.cards
    assert (card.vendor, card.index, card.name, card.total_mib) == (
        "pci-0xfff0",
        0,
        "PCI 0xfff0:0x00aa",
        None,
    )
    assert reading.card_sources == ("sysfs",)
    unread = {u.field: u.why for u in reading.unread}
    assert "card.pci-0xfff0.0.total" in unread
    assert "sysfs" in unread["card.pci-0xfff0.0.total"]


def test_the_second_tool_without_python_is_named_unread(tmp_path: Path) -> None:
    from mcgyvr.fleet import machine as reader

    machine = next(m for m in shapes() if m.label == "other-vendor")
    staged = replace(stage(machine), python=False)
    reading = reader.parse(run(staged, tmp_path).stdout)
    unread = {u.field: u.why for u in reading.unread}
    assert "python3" in unread["cards.rocm-smi"]
    # With no tool answering for its vendor, its cards are read from sysfs.
    assert reading.card_sources == ("sysfs",)
    assert {c.vendor for c in reading.cards} == {"amd"}


def test_the_second_tools_name_falls_back_to_its_model(tmp_path: Path) -> None:
    from mcgyvr.fleet import machine as reader

    text = json.dumps(
        {
            "card0": {
                "Card model": "Example Model R",
                "VRAM Total Memory (B)": str(6007 * MIB),
                "VRAM Total Used Memory (B)": "0",
            }
        }
    ).encode()
    reading = reader.parse(run(Staged(second_tool=text), tmp_path).stdout)
    (card,) = reading.cards
    assert card.name == "Example Model R"


@pytest.mark.parametrize(
    ("pci", "vendor"),
    [
        ("0x10de", "nvidia"),
        ("0x1002", "amd"),
        ("0x8086", "intel"),
        ("0xFFF0", "pci-0xfff0"),
    ],
)
def test_sysfs_names_a_cards_vendor_by_the_vendor_table(
    pci: str, vendor: str, tmp_path: Path
) -> None:
    from mcgyvr.fleet import machine as reader

    staged = Staged(sysfs=(SysfsCard(number=3, vendor=pci, device="0x00bb"),))
    reading = reader.parse(run(staged, tmp_path).stdout)
    (card,) = reading.cards
    assert (card.vendor, card.index) == (vendor, 3)


@pytest.mark.parametrize("bounded", [True, False], ids=["timeout", "no-timeout"])
def test_code_in_the_working_folder_does_not_read_the_second_tools_json(
    bounded: bool, tmp_path: Path
) -> None:
    """A planted ``json.py`` beside the reader changes nothing in the reading."""
    from mcgyvr.fleet import machine as reader

    staged = replace(
        stage(next(m for m in shapes() if m.label == "other-vendor")),
        timeout_program=bounded,
    )
    clean = reader.parse(run(staged, tmp_path / "clean").stdout)
    planted = tmp_path / "planted"
    planted.mkdir()
    (planted / "json.py").write_text(
        "def loads(*a, **k):\n"
        "    return {'card5': {'Card series': 'Planted', "
        "'VRAM Total Memory (B)': '1048576000', "
        "'VRAM Total Used Memory (B)': '0'}}\n",
        encoding="utf-8",
    )
    dirty = reader.parse(run(staged, planted).stdout)
    assert dirty.cards == clean.cards
    assert [c.name for c in dirty.cards if c.name == "Planted"] == []


@pytest.mark.parametrize(
    ("text", "said"),
    [
        (b"{}", "printed no card"),
        (
            json.dumps(
                {
                    "card0": {
                        "Card series": "Example Card Q",
                        "VRAM Total Memory (B)": str(11_111 * MIB),
                        "VRAM Total Used Memory (B)": "0",
                    },
                    "card1": "flat",
                }
            ).encode(),
            "not a JSON object",
        ),
    ],
    ids=["no-card", "an-entry-that-is-not-an-object"],
)
def test_a_second_tool_whose_card_list_may_be_short_gets_no_short_id(
    text: bytes, said: str, tmp_path: Path
) -> None:
    from mcgyvr.fleet import machine as reader

    reading = reader.parse(run(Staged(second_tool=text), tmp_path).stdout)
    assert said in {u.field: u.why for u in reading.unread}["cards.rocm-smi"]
    with pytest.raises(ValueError, match=r"cards\.rocm-smi"):
        reader.short_id(reading)


def test_a_second_tool_size_that_is_not_a_whole_number_says_so(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine as reader

    text = json.dumps(
        {
            "card0": {
                "Card series": "Example Card Q",
                "VRAM Total Memory (B)": 11_111.5 * MIB,
                "VRAM Total Used Memory (B)": "0",
            }
        }
    ).encode()
    reading = reader.parse(run(Staged(second_tool=text), tmp_path).stdout)
    why = {u.field: u.why for u in reading.unread}["card.amd.0.total"]
    assert "not a whole number" in why


def test_a_second_tool_name_with_a_no_break_space_is_read_as_it_is(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine as reader

    text = json.dumps(
        {
            "card0": {
                "Card series": "Example\u00a0Card Q",
                "VRAM Total Memory (B)": str(11_111 * MIB),
                "VRAM Total Used Memory (B)": "0",
            }
        }
    ).encode()
    reading = reader.parse(run(Staged(second_tool=text), tmp_path).stdout)
    (card,) = reading.cards
    assert card.name == "Example\u00a0Card Q"
