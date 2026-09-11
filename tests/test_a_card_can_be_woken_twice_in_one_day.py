"""A card can be woken twice in one day.

RED, against code that exists. P0 of ``records/plans/fleet-identity.md`` §11.

The Waker gives every wake a RUN_ID of its own (``--suffix``,
``src/mcgyvr/wake.py:128-150``). But the serve steps declare fixed artifact
names (``# RUN_ARTIFACTS: serve-up.json`` in
``src/mcgyvr/serving/gate-scripts/serve-up.py``), filed under one envelope per
day and campaign (``records/evidence/<date>-live-<host>/``), and gate 5 refuses
a declared artifact that already exists
(``src/mcgyvr/serving/gate-scripts/05-envelope.py:281-289``). A suffix changes
the RUN_ID and not the file name, so the second ``serve up`` of one host on one
day is refused (``records/measurements/flexibility-2026-09-09/README.md``,
Defects: "The Waker cannot wake one card twice in a day"). A waker that works
once a day is not a waker, and every switch that wakes a unit goes through it.
"""

from __future__ import annotations

from pathlib import Path

from tests import onedoor
from tests.test_the_door_serves_a_ladder_and_leaves_it_up import UNITS, compose_file


def test_a_second_serve_up_on_one_day_is_not_refused_for_the_first_ones_record(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    stubs = onedoor.stubs_dir(root)

    onedoor.serving(stubs, UNITS)
    first = onedoor.serve_door(root, "up", compose, suffix="wake-1")
    assert first.returncode == 0, first.stderr[-1500:]
    down = onedoor.serve_door(root, "down", compose, suffix="sleep-1")
    assert down.returncode == 0, down.stderr[-1500:]

    onedoor.serving(stubs, UNITS)
    again = onedoor.serve_door(root, "up", compose, suffix="wake-2")

    assert "already exists" not in again.stderr, (
        "the day's second wake was refused for the first wake's serve-up.json: "
        f"{again.stderr[-1500:]}"
    )
    assert again.returncode == 0, again.stderr[-1500:]
