"""A field the machine reader cannot read names itself and why.

A field that cannot be read is left ``null`` in the reading and listed as
unread, with a reason that says why; it is never filled with a guess and never
makes the reader fail. Over every invented machine the unread fields are
exactly the ones the machine cannot give, and a tool that fails or a missing
machine-id file each name what they cost.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.machine_shapes import Shape, shape, shapes
from tests.machinereader import (
    FIRST_TOOL,
    MIB,
    Staged,
    SysfsCard,
    expected_unread,
    fingerprint,
    reading,
    replace,
    run,
    stage,
    unread,
)


def _read(staged: Staged, where: Path) -> dict[str, Any]:
    ran = run(staged, where)
    assert ran.returncode == 0, ran.stderr
    return reading(ran.stdout)


def _unread(staged: Staged, where: Path) -> dict[str, str]:
    return unread(_read(staged, where))


def _card(document: dict[str, Any], index: int) -> dict[str, Any]:
    found: list[dict[str, Any]] = [c for c in document["cards"] if c["index"] == index]
    assert len(found) == 1, document
    return found[0]


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_the_unread_fields_are_exactly_the_ones_the_machine_cannot_give(
    machine: Shape, tmp_path: Path
) -> None:
    named = _unread(stage(machine), tmp_path)
    assert set(named) == expected_unread(machine)
    assert all(why.strip() for why in named.values()), named


def test_a_size_the_tool_prints_as_not_available_is_unread_and_says_so(
    tmp_path: Path,
) -> None:
    document = _read(stage(shape("unreadable-size")), tmp_path)
    assert "[N/A]" in unread(document)["card.nvidia.1.total"]
    card = _card(document, 1)
    assert (card["name"], card["total_mib"], card["used_mib"], card["free_mib"]) == (
        "Example Card J",
        None,
        None,
        None,
    )


def test_a_first_tool_that_fails_is_named_with_its_exit_status(
    tmp_path: Path,
) -> None:
    staged = replace(stage(shape("one-card")), first_tool=b"", first_tool_exit=9)
    named = _unread(staged, tmp_path)
    assert FIRST_TOOL in named["cards.nvidia-smi"]
    assert "9" in named["cards.nvidia-smi"]


def test_without_a_machine_id_file_the_id_is_derived_from_the_host_name(
    tmp_path: Path,
) -> None:
    document = _read(Staged(machine_id_file=None, hostname="box-2.example"), tmp_path)
    assert document["machine"]["id"] == fingerprint("host:box-2.example")
    assert document["machine"]["id_from"] == "hostname"
    assert document["unread"] == []


def test_with_a_machine_id_file_the_id_says_which_file(tmp_path: Path) -> None:
    document = _read(Staged(machine_id_file="00ff" * 8), tmp_path)
    assert document["machine"]["id"] == fingerprint("00ff" * 8)
    assert document["machine"]["id_from"] == "/etc/machine-id"


def test_without_a_machine_id_file_or_a_host_name_both_are_named_unread(
    tmp_path: Path,
) -> None:
    document = _read(Staged(machine_id_file=None, hostname=None), tmp_path)
    assert (document["machine"]["id"], document["machine"]["host"]) == ("", "")
    named = unread(document)
    assert named["machine_id"].strip()
    assert named["host"].strip()


def test_a_first_tool_that_answers_with_no_card_is_named_unread(
    tmp_path: Path,
) -> None:
    why = _unread(Staged(first_tool=b""), tmp_path)["cards.nvidia-smi"]
    assert "printed no card" in why
    assert "left over" in why


def test_a_failing_tool_is_named_with_what_the_user_can_do(tmp_path: Path) -> None:
    why = _unread(Staged(first_tool=b"", first_tool_exit=4), tmp_path)[
        "cards.nvidia-smi"
    ]
    assert "Run nvidia-smi by hand" in why


def test_a_second_tool_reporting_more_used_than_total_names_free_unread(
    tmp_path: Path,
) -> None:
    text = json.dumps(
        {
            "card0": {
                "Card series": "Example Card S",
                "VRAM Total Memory (B)": str(3001 * MIB),
                "VRAM Total Used Memory (B)": str(3002 * MIB),
            }
        }
    ).encode()
    document = _read(Staged(second_tool=text), tmp_path)
    card = _card(document, 0)
    assert (card["vendor"], card["total_mib"], card["used_mib"], card["free_mib"]) == (
        "amd",
        3001,
        3002,
        None,
    )
    assert "more memory used" in unread(document)["card.amd.0.free"]


def test_sysfs_reporting_more_used_than_total_names_free_unread(
    tmp_path: Path,
) -> None:
    card = SysfsCard(
        number=0,
        vendor="0x1002",
        device="0x00cc",
        product_name="Example Card T",
        vram_total_bytes=3001 * MIB,
        vram_used_bytes=3002 * MIB,
    )
    document = _read(Staged(sysfs=(card,)), tmp_path)
    read = _card(document, 0)
    assert (read["name"], read["total_mib"], read["used_mib"], read["free_mib"]) == (
        "Example Card T",
        3001,
        3002,
        None,
    )
    assert "more memory used" in unread(document)["card.amd.0.free"]


@pytest.mark.parametrize(
    "hostname", ["bad host", "boxé.example", "x" * 254, "box;1.example"]
)
def test_a_host_name_a_host_name_cannot_be_is_named_unread(
    hostname: str, tmp_path: Path
) -> None:
    document = _read(Staged(hostname=hostname), tmp_path)
    assert document["machine"]["host"] == ""
    assert unread(document)["host"].strip()


def test_the_machine_id_is_taken_from_the_first_machine_id_file_first(
    tmp_path: Path,
) -> None:
    staged = Staged(machine_id_file="aa" * 16, dbus_machine_id_file="bb" * 16)
    document = _read(staged, tmp_path)
    assert document["machine"]["id"] == fingerprint("aa" * 16)
    assert document["machine"]["id_from"] == "/etc/machine-id"


def test_a_blank_first_machine_id_file_gives_way_to_the_second(
    tmp_path: Path,
) -> None:
    staged = Staged(machine_id_file="   ", dbus_machine_id_file="bb" * 16)
    document = _read(staged, tmp_path)
    assert document["machine"]["id"] == fingerprint("bb" * 16)
    assert document["machine"]["id_from"] == "/var/lib/dbus/machine-id"


@pytest.mark.parametrize(
    ("staged", "field"),
    [
        (
            Staged(first_tool=b"0, 7919, 0, 7919, Exa\x00mple Card\n"),
            "card.nvidia.0.name",
        ),
        (
            Staged(first_tool=b"0, 79\x0019, 0, 7919, Example Card\n"),
            "card.nvidia.0.total",
        ),
        (
            Staged(
                sysfs=(
                    SysfsCard(
                        number=0,
                        vendor="0x1002",
                        device="0x00aa",
                        product_name="Example Card",
                        raw={"mem_info_vram_total": b"83\x0088608\n"},
                    ),
                )
            ),
            "card.amd.0.total",
        ),
        (Staged(machine_id_file=b"0123456789ab\x00cdef\n"), "machine_id"),
        (Staged(hostname=b"box\x00-1.example\n"), "host"),
    ],
    ids=["tool-name", "tool-size", "sysfs-size", "machine-id", "host"],
)
def test_a_nul_byte_changes_no_value_it_is_named_unread(
    staged: Staged, field: str, tmp_path: Path
) -> None:
    """A NUL is taken as the control character it is, never dropped."""
    assert field in _unread(staged, tmp_path)


def test_a_control_character_in_the_machine_id_file_is_named_not_hashed(
    tmp_path: Path,
) -> None:
    document = _read(Staged(machine_id_file=b"0123456789ab\x1bcdef\n"), tmp_path)
    assert document["machine"]["id"] == ""
    assert "machine_id" in unread(document)


def test_a_machine_id_file_with_a_line_too_long_is_named_not_passed_over(
    tmp_path: Path,
) -> None:
    """Passing over it for the host name would give the machine another id."""
    staged = Staged(machine_id_file="a" * 5000, hostname="box-2.example")
    document = _read(staged, tmp_path)
    assert document["machine"]["id"] == ""
    assert "more than a line" in unread(document)["machine_id"]


def test_a_name_file_with_a_line_too_long_names_the_name_unread(
    tmp_path: Path,
) -> None:
    card = SysfsCard(
        number=0,
        vendor="0x1002",
        device="0x00aa",
        product_name="N" * 5000,
        vram_total_bytes=8191 * MIB,
        vram_used_bytes=0,
    )
    document = _read(Staged(sysfs=(card,)), tmp_path)
    assert _card(document, 0)["name"] is None
    assert "longer than" in unread(document)["card.amd.0.name"]


@pytest.mark.parametrize("seconds", [0, 1234567])
def test_a_time_bound_that_is_not_one_is_not_taken(
    seconds: int, tmp_path: Path
) -> None:
    """Zero would mean no bound at all; seven digits is past what is taken."""
    assert "above 0" in _unread(Staged(tool_seconds=seconds), tmp_path)["tool_bound"]
