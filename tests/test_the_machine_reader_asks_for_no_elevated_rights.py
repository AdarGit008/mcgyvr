"""The machine reader asks for no elevated rights.

The reader names no command that raises rights or reads what only raised rights
may, and over every invented machine it calls none of them and asks no card
tool anything but the questions it is known to ask. It reads no file but under
its root: every path it names is under that root, except ``/dev/null``.
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


def _code_lines(text: str) -> list[str]:
    """The script's lines that are not comments."""
    return [line for line in text.splitlines() if not line.lstrip().startswith("#")]


#: A path from the file system's top, not written under the reader's root.
_ABSOLUTE = re.compile(r"(?<![\w$}*])/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+")


def test_the_reader_names_no_file_outside_its_root() -> None:
    text = READER.read_text(encoding="utf-8")
    found = []
    for line in _code_lines(text):
        for match in _ABSOLUTE.finditer(line):
            path = match.group(0)
            before = line[: match.start()]
            if path == "/dev/null" or before.endswith(("$ROOT", '"$ROOT')):
                continue
            found.append(path)
    assert not found, f"machine-read.sh names files outside its root: {found}"
