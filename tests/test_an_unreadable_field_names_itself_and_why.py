"""A field the machine reader cannot read names itself and why.

A field that cannot be read is left empty in the reading and listed as unread,
with a reason that says why; it is never filled with a guess and never makes
the reader fail. Over every invented machine the unread fields are exactly the
ones the machine cannot give, and a tool that fails, a container tool that is
absent or refused, or a missing machine-id file each name what they cost.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.machine_shapes import Shape, shape, shapes
from tests.machinereader import (
    FIRST_TOOL,
    Staged,
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
