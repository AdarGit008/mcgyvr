"""One kind of run: held to the live lock whenever a fleet is live, but a staged one.

There is no ``profile: live|dev`` any more (owner, 2026-10-15: all dev items
are the lab's). What a run is held to follows from the setup it runs under and
whether a fleet is live (:func:`mcgyvr.fleet.roots.runs_live`):

* a setup in the data folder — the staging folder ``mcgyvr setup`` starts and
  samples before anything of it is locked — is held to nothing, live fleet or
  none;
* any other setup is held to the live fleet's lock whenever a fleet is live:
  the live fleet's own, and one a person names with ``--config``;
* a setup held in memory, with no folder (``None``), is held on the same
  terms as one a person names;
* with no fleet live, a setup outside the config folder is held to nothing,
  and one in the config folder is held to the lock all the same (which then
  refuses it). Gate 1 holds a run under no config at all to the lock, live
  or not (``tests/test_gate_1_admits_a_live_serve_up_only_from_the_fleet_lock.py``).

A ``fleet.yaml`` that still says ``profile:`` is refused, as any key the file
does not hold is, and the lease a run writes on a rig names no profile.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcgyvr.fleet.files import FleetFileError, load_fleet
from mcgyvr.fleet.roots import runs_live
from mcgyvr.serving.gatelib import Lease, new_lease


def _live(home: Path) -> None:
    """Name a fleet live in the config folder at ``home``."""
    (home / "live.json").write_text(json.dumps({"fleet": "own"}), encoding="utf-8")


@pytest.fixture
def folders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """The config folder and the data folder, both empty: ``(home, data)``."""
    home, data = tmp_path / "home", tmp_path / "data"
    (home / "fleets" / "own").mkdir(parents=True)
    data.mkdir()
    monkeypatch.setenv("MCGYVR_HOME", str(home))
    monkeypatch.setenv("MCGYVR_DATA", str(data))
    return home, data


def test_a_setup_held_in_memory_is_held_to_the_lock_once_a_fleet_is_live(
    folders: tuple[Path, Path],
) -> None:
    home, _ = folders
    assert not runs_live(None)
    _live(home)
    assert runs_live(None)


def test_a_setup_in_the_config_folder_is_held_to_the_lock(
    folders: tuple[Path, Path],
) -> None:
    home, _ = folders
    assert runs_live(home / "fleets" / "own")
    assert runs_live(home)


def test_a_staged_setup_in_the_data_folder_is_held_to_nothing(
    folders: tuple[Path, Path],
) -> None:
    home, data = folders
    staged = data / "setup" / "20261015T000000-abcdef01"
    staged.mkdir(parents=True)
    assert not runs_live(staged)
    _live(home)
    assert not runs_live(staged), "a fleet being live does not reach the staging"


def test_a_setup_a_person_names_is_held_to_the_lock_once_a_fleet_is_live(
    folders: tuple[Path, Path], tmp_path: Path
) -> None:
    home, _ = folders
    own = tmp_path / "my-setup"
    own.mkdir()
    assert not runs_live(own), "with no fleet live there is no lock to hold it to"
    _live(home)
    assert runs_live(own)


def test_a_pointer_that_cannot_be_read_holds_a_run_to_the_lock(
    folders: tuple[Path, Path], tmp_path: Path
) -> None:
    home, _ = folders
    (home / "live.json").write_text("{not json", encoding="utf-8")
    assert runs_live(tmp_path / "my-setup")


@pytest.mark.parametrize("value", ["live", "dev"])
def test_a_fleet_file_that_names_a_profile_is_refused(value: str) -> None:
    text = f"profile: {value}\nunits:\n  local:\n    address: http://a:1\n"
    with pytest.raises(FleetFileError, match="profile"):
        load_fleet(text)


def test_a_lease_names_no_profile() -> None:
    lease = new_lease("live-srv1", "serve-up", 4242)
    assert "profile=" not in lease.line()
    parsed = Lease.parse(lease.line())
    assert parsed is not None and parsed.lease_id == lease.lease_id
    assert not hasattr(parsed, "profile")
