"""The machine reader asks for no elevated rights.

The reader names no command that raises rights or reads what only raised rights
may, and over every invented machine it calls none of them and asks no card
tool anything but the questions it is known to ask.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.machine_shapes import Shape, shapes
from tests.machinereader import ELEVATION, READER, run, stage


def test_the_reader_names_no_command_that_raises_rights() -> None:
    text = READER.read_text(encoding="utf-8")
    named = sorted(
        {word for word in ELEVATION if re.search(rf"(?<![\w.-]){word}(?![\w-])", text)}
    )
    assert not named, f"machine-read.sh names {named}"


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_reading_a_machine_calls_no_command_that_raises_rights(
    machine: Shape, tmp_path: Path
) -> None:
    ran = run(stage(machine), tmp_path)
    assert ran.returncode == 0, ran.stderr
    assert ran.elevated == ()
    assert ran.unexpected == ()
