"""A fleet folder holds its lock in a folder named ``lock``.

The lock tree inside a fleet folder is a neutral ``lock/``,
not ``records/fleet``, with no migration. A live fleet folder, a stamp folder
and the dev root all hold it there (:data:`mcgyvr.fleet.roots.LOCK_DIR`), and
every reader looks there: the lock writer, promotion, admission, the alert
pull and the door's gate 1.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcgyvr import cli
from mcgyvr.fleet.roots import LOCK_DIR, fleets_dir, live_fleet
from tests import setup_door as sd


def test_the_lock_folder_is_named_lock() -> None:
    from mcgyvr.fleet import lock, promote

    assert Path("lock") == LOCK_DIR == lock.LOCK_DIR == promote.LOCK_DIR


def test_a_fleet_setup_made_live_holds_its_lock_and_records_in_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sd.interactive(
        monkeypatch,
        sd.FakeRig(),
        {"Start the serving containers": True, "Lock the fleet": True},
    )
    assert cli.main(["setup"]) == 0
    name = live_fleet()
    assert name is not None
    folder = fleets_dir() / name

    lock = json.loads((folder / "lock" / "own.json").read_text(encoding="utf-8"))
    assert "layout_sha256" in lock
    assert list((folder / "lock" / "rigs").glob("*/cmb-*.json"))
    assert not (folder / "records").exists()
