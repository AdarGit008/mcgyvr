"""Gate 1 lets a live ``serve up`` through only for units the fleet lock names.

RED. Gate 1 (``src/mcgyvr/serving/gate-scripts/01-round.py``) settles a run's
profile and round and asks nothing about what a live ``serve up`` starts:
under the default profile (``live``, ruling R4, ``01-round.py:20``) it brings
up any compose file. The intent is ``records/plans/fleet-identity.md`` §6
(owner, 2026-09-10).

A live ``serve up`` is admitted only if its units are in the fleet lock for
that rig, and then it is admitted: a gate that refused every live up would be
production down. A live ``serve down`` is always admitted, because stopping
starts nothing unapproved and it is the way out of a rig left in a state nobody
locked. That half needs no new test: in
``tests/test_the_door_serves_a_ladder_and_leaves_it_up.py``,
``test_serve_down_opens_on_the_serving_rig_and_requires_nothing_left`` is a
live down with no lock at all, and it stays green.

Gate 1 reaches no rig, so the refusal costs no rig time. When this goes green,
the door tests that ``serve up`` under the default profile with no lock declare
``profile: dev`` in the same change (plan §10).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from tests import onedoor
from tests.red_port.conftest import required
from tests.test_the_door_serves_a_ladder_and_leaves_it_up import UNITS, compose_file

#: The fixture's two llama.cpp units on srv1, as the lock names them.
SLOTS: list[Any] = [["a", "awake"], ["b", "awake"]]
SRV1_FLEET: dict[str, Any] = {
    "rigs": {"srv1": {"rig_id": "rig-" + "1" * 64}},
    "units": {
        name: {
            "rig": "srv1",
            "unit_id": "unt-" + digit * 64,
            "engine": "llama.cpp",
            "address": f"http://srv1:{8001 + index}",
            "container": container,
            "image": "llamacpp:b10644-L3",
            "command": ["--model", "/models/x.gguf", "--port", str(8001 + index)],
            "room_mib": 2000,
            "width": 1,
            "window": 4096,
            "output_tokens": 512,
            "request_timeout_s": 120.0,
        }
        for index, (name, digit, container) in enumerate(
            (("a", "a", UNITS[0]), ("b", "b", UNITS[1]))
        )
    },
    "fleets": {"flt-01": {"layout": {"srv1": SLOTS}, "next": []}},
}
SRV1_EVIDENCE: dict[str, Any] = {
    "rigs": {"srv1": {"card_mib": 6144, "overhead_mib": 400}},
    "combinations": [
        {
            "rig": "srv1",
            "slots": SLOTS,
            "passed": True,
            "overhead_mib": 400,
            "restarts": {"a": 0, "b": 0},
            "warm_decode_tok_s": {"a": 20.0, "b": 20.0},
            "baseline_tok_s": {"a": 20.5, "b": 20.5},
            "card_peak_mib": {"a": 2000, "b": 2000},
            "prefill_tok_s": {"a": 1450.0, "b": 1450.0},
            "validated_at": "2026-09-11T10:00:00Z",
            "envelope": "records/evidence/2026-09-11-fleet-srv1/flt-01",
        }
    ],
    "moves": [],
}


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
    lock.write(
        root,
        SRV1_FLEET,
        SRV1_EVIDENCE,
        policy={"ladder": ["a", "b"]},
        tolerances={"warm_decode_pct": {"llama.cpp": 5.0}},
    )
    onedoor.serving(onedoor.stubs_dir(root), UNITS)

    result = onedoor.serve_door(root, "up", compose)

    assert result.returncode == 0, (result.stdout, result.stderr[-1500:])
    assert _brought_up(root, compose), onedoor.docker_log(root)
