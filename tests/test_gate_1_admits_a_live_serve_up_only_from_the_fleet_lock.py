"""Gate 1 lets a live ``serve up`` through only for units the fleet lock names.

A live ``serve up`` is admitted only if its units are in the fleet lock for
that rig, and then it is admitted: a gate that refused every live up would be
production down. A live ``serve down`` is always admitted, because stopping
starts nothing unapproved and it is the way out of a rig left in a state nobody
locked. That half needs no new test: in
``tests/test_the_door_serves_a_ladder_and_leaves_it_up.py``,
``test_serve_down_opens_on_the_serving_rig_and_requires_nothing_left`` is a
live down with no lock at all, and it stays green.

Gate 1 reaches no rig, so the refusal costs no rig time.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from tests import onedoor
from tests.doors import UNITS, compose_file
from tests.fleetlocks import BOX1_EVIDENCE, BOX1_FLEET
from tests.red_port.conftest import required


def _brought_up(root: Path, compose: Path) -> bool:
    return any(
        line.startswith(f"compose -f {compose} -p mcgyvr up -d")
        for line in onedoor.docker_log(root)
    )


def test_a_live_serve_up_no_fleet_lock_names_is_refused_before_any_rig(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    onedoor.serving(onedoor.stubs_dir(root), UNITS)

    result = onedoor.serve_door(root, "up", compose)

    refused = (
        result.returncode != 0
        and "gate 1:" in result.stderr
        and "fleet lock" in result.stderr
    )
    assert refused, (
        "a live serve up of units no fleet lock names must be refused at gate 1, "
        f"naming the fleet lock.\nexit {result.returncode}\n"
        f"stderr: {result.stderr[-1500:]}"
    )
    assert onedoor.ssh_log(root) == [], "a rig was read before the refusal"
    assert not _brought_up(root, compose), onedoor.docker_log(root)


def test_a_live_serve_up_of_units_the_fleet_lock_names_is_admitted(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    lock = required(
        "write the fleet lock from passing dev runs, refusing what it cannot pin",
        lambda: importlib.import_module("mcgyvr.fleet.lock"),
    )
    # The live lock is the fleet folder ~/.mcgyvr/live.json names (HOME is the
    # test's own), never a lock under the door's run root.
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
    onedoor.serving(onedoor.stubs_dir(root), UNITS)

    result = onedoor.serve_door(root, "up", compose)

    assert result.returncode == 0, (result.stdout, result.stderr[-1500:])
    assert _brought_up(root, compose), onedoor.docker_log(root)
