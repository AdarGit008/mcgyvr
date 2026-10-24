"""The setup wizard starts every rig's units at once, not one rig after another.

Each rig's ``serve up`` waits until that rig's units answer, so a wizard that
started rigs in turn would make each rig wait for the ones before it. The
doors run side by side, one per rig; a rig whose up fails does not stop the
others, and the step fails naming every rig that failed.

The machines here are invented.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from pathlib import Path

import pytest

from mcgyvr import scan as scan_module
from mcgyvr.cli.commands.setup import _setup_start, _SetupInteractiveError
from mcgyvr.serving import spec_name

RIGS = {"rig-d": "rig-d.example", "rig-e": "rig-e.example", "rig-f": "rig-f.example"}


def scans(tmp_path: Path) -> dict[str, scan_module.Scan]:
    found = {}
    for rig, host in RIGS.items():
        (tmp_path / spec_name(host)).write_text("services: {}", encoding="utf-8")
        found[rig] = scan_module.Scan(
            machine=scan_module.Machine(id=f"id-{rig}", host=host, kernel="k")
        )
    return found


def host_of(argv: Sequence[str]) -> str:
    return argv[list(argv).index("--host") + 1]


def test_every_rigs_door_runs_while_the_others_do(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each fake door waits until all three are running: started in turn, the
    first would wait for the others forever, and the barrier breaks."""
    meeting = threading.Barrier(len(RIGS), timeout=10)
    seen: list[str] = []

    def door(argv: Sequence[str], **_: object) -> int:
        meeting.wait()
        seen.append(host_of(argv))
        return 0

    monkeypatch.setattr("mcgyvr.wake.spawn_door", door)
    _setup_start(list(RIGS), scans(tmp_path), tmp_path)
    assert sorted(seen) == sorted(RIGS)


def test_a_failed_rig_does_not_stop_the_others_and_every_failure_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    def door(argv: Sequence[str], **_: object) -> int:
        seen.append(host_of(argv))
        return 0 if host_of(argv) == "rig-e" else 1

    monkeypatch.setattr("mcgyvr.wake.spawn_door", door)
    with pytest.raises(_SetupInteractiveError) as raised:
        _setup_start(list(RIGS), scans(tmp_path), tmp_path)
    assert sorted(seen) == sorted(RIGS)
    said = str(raised.value)
    assert "rig-d: serve up exited 1" in said
    assert "rig-f: serve up exited 1" in said
    assert "rig-e" not in said
