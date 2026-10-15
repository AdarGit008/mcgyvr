"""A card of another vendor than the first tool's is read by its name and size.

The one reader (:mod:`mcgyvr.serving.rigscan`) asks the first vendor's tool and
the second vendor's, and takes from sysfs the cards of any vendor no answering
tool covered. A card the second vendor's tool reads, or one sysfs publishes a
size for, is in the reading with its name and its total memory. A card sysfs
publishes no name or size for is still in the reading, named by its bus ids,
and its size is named as unread. The reader is shipped as ``python3 -I -B -``, so
the second tool's JSON is read by code the reader brings, never by code found
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
    cards,
    expected_cards,
    machine_reading,
    reading,
    run,
    stage,
    unread,
)

OTHER = [m for m in shapes() if any(c.vendor == "vendor-b" for c in m.cards)]


def _read(staged: Staged, where: Path) -> dict[str, object]:
    ran = run(staged, where)
    assert ran.returncode == 0, ran.stderr
    return reading(ran.stdout)


def _second(**entries: object) -> bytes:
    return json.dumps(entries).encode()


@pytest.mark.parametrize("machine", OTHER, ids=lambda m: m.label)
def test_every_card_of_the_other_vendor_is_read_by_name_and_size(
    machine: Shape, tmp_path: Path
) -> None:
    document = machine_reading(machine, tmp_path)
    wanted = [c for c in expected_cards(machine) if c[0] == "amd"]
    assert wanted
    got = [card[:4] for card in cards(document) if card[0] == "amd"]
    assert got == [c[:4] for c in wanted]
    assert all(name for _, _, name, _ in got)
    assert all(total is not None for *_, total in got)


def test_a_machine_of_two_vendors_is_read_by_both_tools(tmp_path: Path) -> None:
    mixed = next(m for m in shapes() if m.label == "mixed-vendors")
    document = machine_reading(mixed, tmp_path)
    assert document["card_sources"] == ["nvidia-smi", "rocm-smi"]
    assert {card[0] for card in cards(document)} == {"nvidia", "amd"}


def test_the_second_tools_keys_are_read_whatever_their_case(tmp_path: Path) -> None:
    text = _second(
        card0={
            "CARD SERIES": "Example Card Q",
            "vram total memory (b)": str(11_111 * MIB),
            "VRAM TOTAL USED MEMORY (B)": str(3 * MIB),
        }
    )
    document = _read(Staged(second_tool=text), tmp_path)
    assert cards(document) == [("amd", 0, "Example Card Q", 11_111, 3, 11_111 - 3)]


def test_a_card_sysfs_names_nothing_for_is_named_by_its_bus_ids(
    tmp_path: Path,
) -> None:
    staged = Staged(sysfs=(SysfsCard(number=0, vendor="0xfff0", device="0x00aa"),))
    document = _read(staged, tmp_path)
    assert [card[:4] for card in cards(document)] == [
        ("pci-0xfff0", 0, "PCI 0xfff0:0x00aa", None)
    ]
    assert document["card_sources"] == ["sysfs"]
    why = unread(document)
    assert "card.pci-0xfff0.0.total" in why
    assert "sysfs" in why["card.pci-0xfff0.0.total"]


def test_the_second_tools_name_falls_back_to_its_model(tmp_path: Path) -> None:
    text = _second(
        card0={
            "Card model": "Example Model R",
            "VRAM Total Memory (B)": str(6007 * MIB),
            "VRAM Total Used Memory (B)": "0",
        }
    )
    ((_, _, name, *_),) = cards(_read(Staged(second_tool=text), tmp_path))
    assert name == "Example Model R"


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
    staged = Staged(sysfs=(SysfsCard(number=3, vendor=pci, device="0x00bb"),))
    assert [card[:2] for card in cards(_read(staged, tmp_path))] == [(vendor, 3)]


def test_code_in_the_working_folder_does_not_read_the_second_tools_json(
    tmp_path: Path,
) -> None:
    """A planted ``json.py`` where the reader runs changes nothing in the reading:
    the door ships it isolated, so the folder gives it no module."""
    staged = stage(next(m for m in shapes() if m.label == "other-vendor"))
    clean = _read(staged, tmp_path / "clean")
    planted = tmp_path / "planted"
    planted.mkdir()
    (planted / "json.py").write_text(
        "def loads(*a, **k):\n"
        "    return {'card5': {'Card series': 'Planted', "
        "'VRAM Total Memory (B)': '1048576000', "
        "'VRAM Total Used Memory (B)': '0'}}\n"
        "def dumps(*a, **k):\n"
        "    return '{}'\n",
        encoding="utf-8",
    )
    dirty = _read(staged, planted)
    assert cards(dirty) == cards(clean)
    assert [c for c in cards(dirty) if c[2] == "Planted"] == []


@pytest.mark.parametrize(
    ("text", "said"),
    [
        (b"{}", "printed no card"),
        (
            _second(
                card0={
                    "Card series": "Example Card Q",
                    "VRAM Total Memory (B)": str(11_111 * MIB),
                    "VRAM Total Used Memory (B)": "0",
                },
                card1="flat",
            ),
            "not a JSON object",
        ),
    ],
    ids=["no-card", "an-entry-that-is-not-an-object"],
)
def test_a_second_tool_whose_card_list_may_be_short_gets_no_rig_id(
    text: bytes, said: str, tmp_path: Path
) -> None:
    from mcgyvr.fleet import ids

    document = _read(Staged(second_tool=text), tmp_path)
    assert said in unread(document)["cards.rocm-smi"]
    with pytest.raises(ValueError, match=r"cards\.rocm-smi"):
        ids.rig_id(document)


def test_a_second_tool_size_that_is_not_a_whole_number_says_so(
    tmp_path: Path,
) -> None:
    text = _second(
        card0={
            "Card series": "Example Card Q",
            "VRAM Total Memory (B)": 11_111.5 * MIB,
            "VRAM Total Used Memory (B)": "0",
        }
    )
    why = unread(_read(Staged(second_tool=text), tmp_path))["card.amd.0.total"]
    assert "not a whole number" in why


def test_a_second_tool_name_with_a_no_break_space_is_read_as_it_is(
    tmp_path: Path,
) -> None:
    text = _second(
        card0={
            "Card series": "Example\u00a0Card Q",
            "VRAM Total Memory (B)": str(11_111 * MIB),
            "VRAM Total Used Memory (B)": "0",
        }
    )
    ((_, _, name, *_),) = cards(_read(Staged(second_tool=text), tmp_path))
    assert name == "Example\u00a0Card Q"
