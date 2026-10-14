"""A machine with no card is read as having none, and nothing is named unread.

Whatever card tools it lacks, the one reader (:mod:`mcgyvr.serving.rigscan`)
names the machine and its host, says it found no card, and does not report a
missing tool as a field it could not read.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.machine_shapes import Shape, shapes
from tests.machinereader import Staged, fingerprint, machine_reading, reading, run


@pytest.mark.parametrize(
    "machine", [m for m in shapes() if not m.cards], ids=lambda m: m.label
)
def test_a_machine_with_no_card_is_read_as_having_none(
    machine: Shape, tmp_path: Path
) -> None:
    document = machine_reading(machine, tmp_path)
    assert document["cards"] == []
    assert document["card_sources"] == []
    assert document["unread"] == []
    assert document["machine"]["id"] == fingerprint(machine.machine_id)
    assert document["machine"]["host"] == machine.host


def test_a_machine_with_no_card_tool_and_no_card_in_sysfs_reads_no_card(
    tmp_path: Path,
) -> None:
    ran = run(Staged(), tmp_path)
    assert ran.returncode == 0, ran.stderr
    document = reading(ran.stdout)
    assert (document["cards"], document["card_sources"], document["unread"]) == (
        [],
        [],
        [],
    )
