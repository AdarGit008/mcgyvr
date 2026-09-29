"""A refusal about the live fleet names the pointer it read.

Promise: when mcgyvr refuses because of which fleet is live, or because none
is, the refusal names the pointer file it actually read: the one in the config
folder the user named. It never names the config folder's default in its
place, where a different pointer may say something else.

Nothing is reached: the probe refuses before it would reach any unit, and the
door's first gate is called in this process with the variables the door would
have set.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcgyvr.fleet import probe
from tests._helpers import by_path

REPO = Path(__file__).resolve().parent.parent
GATE_1 = REPO / "src" / "mcgyvr" / "serving" / "gate-scripts" / "01-round.py"
#: The config folder's default, as a refusal must not name it once moved.
DEFAULT_POINTER = "~/.mcgyvr/live.json"
#: A fleet.yaml that loads and holds no fleet.
NO_FLEET = "units:\n  u1:\n    address: http://localhost:8080\n    model: m\n"


def _point(folder: Path, fleet: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    pointer = folder / "live.json"
    pointer.write_text(json.dumps({"fleet": fleet}), encoding="utf-8")
    return pointer


def _moved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A config folder the user named, beside a default one naming a fleet."""
    _point(Path.home() / ".mcgyvr", "at-the-default")
    moved = tmp_path / "settings"
    moved.mkdir()
    monkeypatch.setenv("MCGYVR_HOME", str(moved))
    return moved


def test_a_probe_with_no_fleet_named_live_names_the_pointer_it_looked_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    moved = _moved(tmp_path, monkeypatch)

    with pytest.raises(probe.ProbeError) as refused:
        probe.run()

    said = str(refused.value)
    assert str(moved / "live.json") in said, said
    assert DEFAULT_POINTER not in said, said


def test_a_probe_of_a_fleet_its_folder_does_not_hold_names_the_pointer_it_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    moved = _moved(tmp_path, monkeypatch)
    pointer = _point(moved, "named")
    folder = moved / "fleets" / "named"
    folder.mkdir(parents=True)
    (folder / "fleet.yaml").write_text(NO_FLEET, encoding="utf-8")

    with pytest.raises(probe.ProbeError) as refused:
        probe.run()

    said = str(refused.value)
    assert str(pointer) in said, said
    assert DEFAULT_POINTER not in said, said


def test_the_first_gate_refusing_a_unit_the_live_lock_lacks_names_the_pointer_it_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    moved = _moved(tmp_path, monkeypatch)
    pointer = _point(moved, "named")
    (moved / "fleets" / "named").mkdir(parents=True)
    monkeypatch.setenv("RUN_HOST", "served.invalid")
    monkeypatch.setenv("RUN_SERVE_EXPECTED", "u1")
    gate = by_path("gate_01_round", GATE_1)

    with pytest.raises(SystemExit):
        gate.refuse_unless_the_fleet_lock_names("up", "live")

    said = capsys.readouterr().err
    assert "gate 1:" in said, said
    assert str(pointer) in said, said
    assert DEFAULT_POINTER not in said, said
