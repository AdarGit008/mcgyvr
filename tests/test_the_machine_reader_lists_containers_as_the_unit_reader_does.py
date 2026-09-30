"""The machine reader lists containers as the unit reader lists them.

Each running container is one ``container=NAME,ID,PROJECT,RESTARTS`` line,
spelled exactly as ``rig-units.sh`` spells it, so a reading of either reader
names a container the same way.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from tests.machinereader import REPO, Staged, run

UNITS = REPO / "src" / "mcgyvr" / "serving" / "gate-scripts" / "rig-units.sh"

LISTING = (
    b"1" * 64
    + b"|example-unit|example-project\n"
    + b"2" * 64
    + b"|example, odd  name|\n"
    + b"3" * 64
    + b"|example-three|example project\n"
)
RESTARTS = {"1" * 64: b"0\n", "2" * 64: b"7\n", "3" * 64: b"not a count\n"}


def _containers(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("container=")]


def test_the_machine_reader_lists_containers_as_the_unit_reader_does(
    tmp_path: Path,
) -> None:
    ran = run(Staged(containers=LISTING, restarts=RESTARTS), tmp_path)
    assert ran.returncode == 0, ran.stderr
    mine = _containers(ran.stdout)
    assert len(mine) == 3

    extra = tmp_path / "unit-reader-programs"
    extra.mkdir()
    for name in ("tr", "sed"):
        found = shutil.which(name)
        assert found, f"no {name} on the test's PATH"
        (extra / name).symlink_to(found)
    bash = shutil.which("bash")
    assert bash
    theirs = subprocess.run(
        [bash, "-s"],
        input=UNITS.read_bytes(),
        capture_output=True,
        env={
            "PATH": os.pathsep.join(
                str(p) for p in (tmp_path / "stubs", tmp_path / "programs", extra)
            ),
            "LC_ALL": "C",
        },
        cwd=tmp_path,
        timeout=60,
        check=False,
    )
    # The unit reader goes on to list card processes, which this machine has no
    # tool for; its container lines come first.
    assert _containers(theirs.stdout.decode()) == mine


def test_the_parsed_containers_carry_what_the_lines_say(tmp_path: Path) -> None:
    from mcgyvr.fleet import machine

    ran = run(Staged(containers=LISTING, restarts=RESTARTS), tmp_path)
    reading = machine.parse(ran.stdout)
    assert reading.containers == (
        machine.Container(
            name="example-unit", id="1" * 64, project="example-project", restarts=0
        ),
        machine.Container(
            name="example_odd_name", id="2" * 64, project=None, restarts=7
        ),
        machine.Container(
            name="example-three", id="3" * 64, project="example_project", restarts=None
        ),
    )
