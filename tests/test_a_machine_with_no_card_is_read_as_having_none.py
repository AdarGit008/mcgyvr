"""A machine with no card is read as having none, and nothing is named unread.

Whatever card tools it lacks, the machine reader names the machine and its
host, says it found no card, and does not report a missing tool as a field it
could not read.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.machine_shapes import Shape, shapes
from tests.machinereader import Staged, fingerprint, machine_read_text, run


@pytest.mark.parametrize(
    "machine", [m for m in shapes() if not m.cards], ids=lambda m: m.label
)
def test_a_machine_with_no_card_is_read_as_having_none(
    machine: Shape, tmp_path: Path
) -> None:
    from mcgyvr.fleet import machine as reader

    reading = reader.parse(machine_read_text(machine, tmp_path))
    assert reading.cards == ()
    assert reading.card_sources == ()
    assert reading.unread == ()
    assert reading.machine_id == fingerprint(machine.machine_id)
    assert reading.host == machine.host


def test_a_machine_with_no_card_tool_and_no_card_in_sysfs_reads_cards_none(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine as reader

    ran = run(Staged(), tmp_path)
    assert ran.returncode == 0, ran.stderr
    assert "cards=none" in ran.stdout.splitlines()
    reading = reader.parse(ran.stdout)
    assert (reading.cards, reading.card_sources, reading.unread) == ((), (), ())
