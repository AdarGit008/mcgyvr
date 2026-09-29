"""A field the machine reader cannot read names itself and why.

A field that cannot be read is left empty in the reading and listed as unread,
with a reason that says why; it is never filled with a guess and never makes
the reader fail. Over every invented machine the unread fields are exactly the
ones the machine cannot give, and a tool that fails, a container tool that is
absent or refused, or a missing machine-id file each name what they cost.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.machine_shapes import Shape, shape, shapes
from tests.machinereader import (
    FIRST_TOOL,
    MIB,
    Staged,
    SysfsCard,
    expected_unread,
    fingerprint,
    replace,
    run,
    stage,
)


def _unread(text: str) -> dict[str, str]:
    from mcgyvr.fleet import machine as reader

    return {u.field: u.why for u in reader.parse(text).unread}


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_the_unread_fields_are_exactly_the_ones_the_machine_cannot_give(
    machine: Shape, tmp_path: Path
) -> None:
    ran = run(stage(machine), tmp_path)
    assert ran.returncode == 0, ran.stderr
    unread = _unread(ran.stdout)
    assert set(unread) == expected_unread(machine)
    assert all(why.strip() for why in unread.values()), unread
    for line in ran.stdout.splitlines():
        if line.startswith("unread="):
            assert "," in line and line.split(",", 1)[1].strip(), line


def test_a_size_the_tool_prints_as_not_available_is_unread_and_says_so(
    tmp_path: Path,
) -> None:
    ran = run(stage(shape("unreadable-size")), tmp_path)
    unread = _unread(ran.stdout)
    assert "[N/A]" in unread["card.nvidia.1.total"]
    from mcgyvr.fleet import machine as reader

    card = next(c for c in reader.parse(ran.stdout).cards if c.index == 1)
    assert (card.name, card.total_mib, card.used_mib, card.free_mib) == (
        "Example Card J",
        None,
        None,
        None,
    )


def test_a_first_tool_that_fails_is_named_with_its_exit_status(
    tmp_path: Path,
) -> None:
    staged = replace(stage(shape("one-card")), first_tool=b"", first_tool_exit=9)
    ran = run(staged, tmp_path)
    assert ran.returncode == 0, ran.stderr
    unread = _unread(ran.stdout)
    assert FIRST_TOOL in unread["cards.nvidia-smi"]
    assert "9" in unread["cards.nvidia-smi"]


def test_a_process_listing_that_fails_leaves_that_cards_holders_unread(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine as reader

    staged = stage(shape("busy-beside-free"))
    listing = dict(staged.first_tool_processes)
    listing[0] = (b"", 15)
    ran = run(replace(staged, first_tool_processes=listing), tmp_path)
    reading = reader.parse(ran.stdout)
    by_index = {c.index: c for c in reading.cards}
    assert by_index[0].holders is None
    assert by_index[1].holders == ()
    assert "15" in {u.field: u.why for u in reading.unread}["card.nvidia.0.holders"]


def test_an_absent_container_tool_leaves_the_containers_unread(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine as reader

    reading = reader.parse(run(Staged(containers=None), tmp_path).stdout)
    assert reading.containers is None
    assert "docker" in {u.field: u.why for u in reading.unread}["containers"]


def test_a_refused_container_tool_leaves_the_containers_unread(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine as reader

    staged = Staged(containers=b"permission denied\n", containers_exit=1)
    reading = reader.parse(run(staged, tmp_path).stdout)
    assert reading.containers is None
    assert "docker ps" in {u.field: u.why for u in reading.unread}["containers"]


def test_without_a_machine_id_file_the_id_is_derived_from_the_host_name(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine as reader

    staged = Staged(machine_id_file=None, hostname="box-2.example")
    reading = reader.parse(run(staged, tmp_path).stdout)
    assert reading.machine_id == fingerprint("host:box-2.example")
    assert reading.machine_id_from == "hostname"
    assert reading.unread == ()


def test_with_a_machine_id_file_the_id_says_which_file(tmp_path: Path) -> None:
    from mcgyvr.fleet import machine as reader

    reading = reader.parse(run(Staged(machine_id_file="00ff" * 8), tmp_path).stdout)
    assert reading.machine_id == fingerprint("00ff" * 8)
    assert reading.machine_id_from == "/etc/machine-id"


def test_without_a_machine_id_file_or_a_host_name_both_are_named_unread(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine as reader

    ran = run(Staged(machine_id_file=None, hostname=None), tmp_path)
    assert ran.returncode == 0, ran.stderr
    reading = reader.parse(ran.stdout)
    assert (reading.machine_id, reading.host) == (None, None)
    unread = {u.field: u.why for u in reading.unread}
    assert unread["machine_id"].strip()
    assert unread["host"].strip()


def test_a_first_tool_that_answers_with_no_card_is_named_unread(
    tmp_path: Path,
) -> None:
    ran = run(Staged(first_tool=b""), tmp_path)
    why = _unread(ran.stdout)["cards.nvidia-smi"]
    assert "printed no card" in why
    assert "left over" in why


def test_a_failing_tool_is_named_with_what_the_user_can_do(tmp_path: Path) -> None:
    ran = run(Staged(first_tool=b"", first_tool_exit=4), tmp_path)
    why = _unread(ran.stdout)["cards.nvidia-smi"]
    assert "Run nvidia-smi by hand" in why


def _raw_unread(stdout: str) -> dict[str, str]:
    """The reader's own unread lines, before any parsing."""
    lines = [line for line in stdout.splitlines() if line.startswith("unread=")]
    return dict(line.removeprefix("unread=").split(",", 1) for line in lines)


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
    ran = run(Staged(second_tool=text), tmp_path)
    assert "card=amd,0,3001,3002,,Example Card S" in ran.stdout.splitlines()
    assert "more memory used" in _raw_unread(ran.stdout)["card.amd.0.free"]


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
    ran = run(Staged(sysfs=(card,)), tmp_path)
    assert "card=amd,0,3001,3002,,Example Card T" in ran.stdout.splitlines()
    assert "more memory used" in _raw_unread(ran.stdout)["card.amd.0.free"]


@pytest.mark.parametrize(
    "hostname", ["bad host", "boxé.example", "x" * 254, "box;1.example"]
)
def test_a_host_name_a_host_name_cannot_be_is_named_unread(
    hostname: str, tmp_path: Path
) -> None:
    ran = run(Staged(hostname=hostname), tmp_path)
    assert "host=" in ran.stdout.splitlines()
    assert _raw_unread(ran.stdout)["host"].strip()


def test_the_machine_id_is_taken_from_the_first_machine_id_file_first(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine as reader

    staged = Staged(machine_id_file="aa" * 16, dbus_machine_id_file="bb" * 16)
    reading = reader.parse(run(staged, tmp_path).stdout)
    assert reading.machine_id == fingerprint("aa" * 16)
    assert reading.machine_id_from == "/etc/machine-id"


def test_a_blank_first_machine_id_file_gives_way_to_the_second(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine as reader

    staged = Staged(machine_id_file="   ", dbus_machine_id_file="bb" * 16)
    reading = reader.parse(run(staged, tmp_path).stdout)
    assert reading.machine_id == fingerprint("bb" * 16)
    assert reading.machine_id_from == "/var/lib/dbus/machine-id"


def test_without_a_time_bound_the_reading_says_so(tmp_path: Path) -> None:
    ran = run(Staged(timeout_program=False), tmp_path)
    assert "timeout" in _raw_unread(ran.stdout)["tool_bound"]


def test_the_reading_ends_with_its_end_line(tmp_path: Path) -> None:
    ran = run(stage(shape("several-sizes")), tmp_path)
    assert ran.stdout.splitlines()[-1] == "end="


def test_a_reading_cut_short_names_itself_and_gets_no_short_id(
    tmp_path: Path,
) -> None:
    """Its unread lines come last, so a cut reading may look like a whole one."""
    from mcgyvr.fleet import machine as reader

    lines = run(stage(shape("several-sizes")), tmp_path).stdout.splitlines()
    cut = "\n".join(lines[: len(lines) // 2]) + "\n"
    reading = reader.parse(cut)
    assert any("end line" in u.why for u in reading.unread if u.field == "reading")
    with pytest.raises(ValueError, match="reading"):
        reader.short_id(reading)


@pytest.mark.parametrize(
    ("staged", "field"),
    [
        (
            Staged(
                first_tool=b"0, 7919, 0, 7919, Exa\x00mple Card\n",
                first_tool_processes={0: (b"", 0)},
            ),
            "card.nvidia.0.name",
        ),
        (
            Staged(
                first_tool=b"0, 79\x0019, 0, 7919, Example Card\n",
                first_tool_processes={0: (b"", 0)},
            ),
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
        (Staged(containers=b"abc123|na\x00me|proj\n"), "containers"),
    ],
    ids=["tool-name", "tool-size", "sysfs-size", "machine-id", "host", "container"],
)
def test_a_nul_byte_changes_no_value_it_is_named_unread(
    staged: Staged, field: str, tmp_path: Path
) -> None:
    """A NUL a shell would drop is taken as the control character it is."""
    ran = run(staged, tmp_path)
    assert ran.returncode == 0, ran.stderr
    assert field in _raw_unread(ran.stdout)


def test_a_control_character_in_the_machine_id_file_is_named_not_hashed(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine as reader

    staged = Staged(machine_id_file=b"0123456789ab\x1bcdef\n")
    reading = reader.parse(run(staged, tmp_path).stdout)
    assert reading.machine_id is None
    assert "machine_id" in {u.field for u in reading.unread}


def test_a_machine_id_file_with_a_line_too_long_is_named_not_passed_over(
    tmp_path: Path,
) -> None:
    """Passing over it for the host name would give an id `mcgyvr scan` does not."""
    from mcgyvr.fleet import machine as reader

    staged = Staged(machine_id_file="a" * 5000, hostname="box-2.example")
    reading = reader.parse(run(staged, tmp_path).stdout)
    assert reading.machine_id is None
    assert "longer than" in {u.field: u.why for u in reading.unread}["machine_id"]


def test_a_name_file_with_a_line_too_long_names_the_name_unread(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine as reader

    card = SysfsCard(
        number=0,
        vendor="0x1002",
        device="0x00aa",
        product_name="N" * 5000,
        vram_total_bytes=8191 * MIB,
        vram_used_bytes=0,
    )
    reading = reader.parse(run(Staged(sysfs=(card,)), tmp_path).stdout)
    (read,) = reading.cards
    assert read.name is None
    assert "longer than" in {u.field: u.why for u in reading.unread}["card.amd.0.name"]


def test_a_zero_time_bound_is_not_taken(tmp_path: Path) -> None:
    """Zero would mean no bound at all to `timeout`."""
    ran = run(Staged(tool_seconds=0), tmp_path)
    assert "above 0" in _raw_unread(ran.stdout)["tool_bound"]


def test_an_inherited_option_that_turns_globbing_off_hides_no_card(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine as reader

    card = SysfsCard(
        number=0,
        vendor="0x1002",
        device="0x00aa",
        product_name="Example Card",
        vram_total_bytes=8191 * MIB,
        vram_used_bytes=0,
    )
    staged = Staged(sysfs=(card,), environment={"SHELLOPTS": "noglob"})
    reading = reader.parse(run(staged, tmp_path).stdout)
    assert [c.key for c in reading.cards] == ["card.amd.0"]
