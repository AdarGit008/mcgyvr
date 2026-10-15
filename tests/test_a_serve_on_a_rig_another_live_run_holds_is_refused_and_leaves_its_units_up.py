"""A serve on a rig another live run holds is refused, and leaves its units up.

Owner's ruling, 2026-10-15: "no one can take from no one". A ``serve up`` or a
``serve down`` that finds the rig's lease held by a run that is still live is
refused at gate 2 (``src/mcgyvr/serving/gate-scripts/02-rig.py``), in one line
naming the holder's run and host and saying to wait for it or end it. The
holder's serve units — named ``mcgyvr-<host>-<service>`` by ``mcgyvr emit`` —
are not listed, stopped or removed, and its lease is left as it was.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from tests import onedoor
from tests.doors import HELD_SERVE_LEASE, HELD_SERVE_RUN, UNITS, compose_file
from tests.fleetlocks import BOX1_EVIDENCE, BOX1_FLEET
from tests.red_port.conftest import required


def _live_lock() -> None:
    """The live fleet lock that admits the fixture's two units at gate 1, so
    a ``serve up`` reaches gate 2."""
    lock = required(
        "write the fleet lock from passing dev runs, refusing what it cannot pin",
        lambda: importlib.import_module("mcgyvr.fleet.lock"),
    )
    live = Path.home() / ".mcgyvr"
    live.mkdir(parents=True, exist_ok=True)
    (live / "live.json").write_text('{"fleet": "flt-01"}', encoding="utf-8")
    lock.write(
        live / "fleets" / "flt-01",
        BOX1_FLEET,
        BOX1_EVIDENCE,
        policy={"ladder": ["a", "b"]},
        tolerances={"warm_decode_class_pct": {"llamacpp": 5.0}},
    )


@pytest.mark.parametrize("mode", ["up", "down"])
def test_a_serve_on_a_held_rig_is_refused_and_the_holders_units_stay_up(
    tmp_path: Path, mode: str
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    if mode == "up":
        _live_lock()
    onedoor.plant_lease(root, HELD_SERVE_LEASE)
    onedoor.containers_up(root, *UNITS)

    result = onedoor.serve_door(root, mode, compose)

    assert result.returncode == 2, (result.returncode, result.stderr[-1500:])
    refusal = [line for line in result.stderr.splitlines() if "is held by" in line]
    assert len(refusal) == 1, result.stderr[-1500:]
    assert HELD_SERVE_RUN in refusal[0] and "elsewhere" in refusal[0], refusal[0]
    assert onedoor.docker_log(root) == [], (
        f"a refused serve reached the holder's daemon: {onedoor.docker_log(root)}"
    )
    assert onedoor.read_lease(root) == HELD_SERVE_LEASE + "\n"
    names = (onedoor.stubs_dir(root) / "serving-names").read_text(encoding="utf-8")
    assert names.split() == list(UNITS), "the holder's units are not up"
