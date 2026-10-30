"""The machine reader's short reading asks for no elevated rights.

The short reading (``--cards``), which a rig's hub agent takes on every
heartbeat, calls no command that raises rights or reads what only raised
rights may, over every invented machine, and asks no card tool anything but
the questions it is known to ask. The whole reading asks for raised rights
once, for the snapshot's DDR speed: ``dmidecode`` plainly, then through
``sudo -n``, which never prompts. No other command of the whole reading
raises rights. Off Linux the whole reading raises none: there is no dmidecode to
read there, so it is never tried, through sudo or otherwise.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from tests.machine_shapes import HostShape, Shape, host_shapes, shapes
from tests.machinereader import ELEVATION, run, stage, stage_host


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_reading_a_machine_calls_no_command_that_raises_rights(
    machine: Shape, tmp_path: Path
) -> None:
    ran = run(stage(machine), tmp_path)
    assert ran.returncode == 0, ran.stderr
    assert ran.elevated == ()
    assert ran.unexpected == ()


def test_the_whole_reading_raises_rights_only_without_a_prompt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from mcgyvr.serving import rigscan

    asked: list[tuple[str, ...]] = []

    def run_tool(
        argv: Sequence[str], *, bound: float = 0.0
    ) -> tuple[str | None, str | None]:
        asked.append(tuple(argv))
        return None, "refused by the test"

    monkeypatch.setattr(rigscan, "_run", run_tool)
    monkeypatch.setattr(rigscan, "measure_bandwidth", lambda root="": None)
    rigscan.scan(weights_dir=str(tmp_path / "weights"), root=str(tmp_path / "root"))
    raising = [argv for argv in asked if set(argv) & set(ELEVATION)]
    assert raising == [
        ("dmidecode", "-t", "memory"),
        ("sudo", "-n", "dmidecode", "-t", "memory"),
    ]


def test_the_short_reading_asks_no_command_that_raises_rights(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from mcgyvr.serving import rigscan

    asked: list[tuple[str, ...]] = []

    def run_tool(
        argv: Sequence[str], *, bound: float = 0.0
    ) -> tuple[str | None, str | None]:
        asked.append(tuple(argv))
        return None, None

    monkeypatch.setattr(rigscan, "_run", run_tool)
    rigscan.read_machine(root=str(tmp_path / "root"))
    assert asked
    assert not [argv for argv in asked if set(argv) & set(ELEVATION)]


@pytest.mark.parametrize(
    "machine",
    [m for m in host_shapes() if m.system != "linux"],
    ids=lambda m: m.label,
)
def test_the_whole_reading_off_linux_raises_no_rights(
    machine: HostShape, tmp_path: Path
) -> None:
    staged = stage_host(machine)
    home = {"HOME": "{where}/home", "MCGYVR_WEIGHTS": "{where}/weights"}
    staged = dataclasses.replace(staged, environment={**staged.environment, **home})
    ran = run(staged, tmp_path, command=(sys.executable, "-I", "-B", "-"))
    assert ran.returncode == 0, ran.stderr
    assert ran.elevated == ()
    assert ran.unexpected == ()
    unread = {u["field"] for u in json.loads(ran.stdout)["unread"]}
    assert "snapshot.ram_mt_s" in unread
