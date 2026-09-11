"""``serve up`` records how many times each unit restarted.

RED, against code that exists. P0 of ``records/plans/fleet-identity.md`` §11.

Restarts are held at exactly 0: a restart fails a dev validation and is never
locked, and on live it alerts and pulls its combination (plan §5). The one
place a unit's start is recorded is ``serve-up.json``, and its rows are what
``servelib.wait_for`` returns (``src/mcgyvr/serving/gate-scripts/serve-up.py:84-92``,
``src/mcgyvr/serving/servelib.py:257-300``): container, port, healthy,
sleeping, seconds, models. No restart count. The one restart pattern on record
is a vLLM pair started ``service_started`` on srv2, where one unit restarts in
every arm (``records/evidence/2026-09-10-tolerance-survey/analysis.txt:673-696``).
"""

from __future__ import annotations

import json
from pathlib import Path

from tests import onedoor
from tests.test_the_door_serves_a_ladder_and_leaves_it_up import UNITS, compose_file


def test_serve_up_files_a_restart_count_for_every_unit(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    onedoor.serving(onedoor.stubs_dir(root), UNITS)

    result = onedoor.serve_door(root, "up", compose)
    assert result.returncode == 0, (result.stdout, result.stderr[-1500:])

    record = json.loads(
        (onedoor.envelope(root, "live-srv1") / "serve-up.json").read_text()
    )
    uncounted = [
        unit["container"]
        for unit in record["units"]
        if not isinstance(unit.get("restarts"), int)
    ]
    assert uncounted == [], (
        f"serve-up.json must record each unit's restart count; none for {uncounted}"
    )
