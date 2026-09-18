"""A card can be woken twice in one day.

The Waker gives every wake a RUN_ID of its own (``--suffix``,
``mcgyvr.wake``), and the serve steps declare a fixed artifact name filed under
one envelope per day and campaign (``records/evidence/<date>-live-<host>/``). A
suffix changes the RUN_ID and not the file name, so the serve steps declare the
file as one they may write again (``# RUN_REWRITES: serve-up.json`` in
``src/mcgyvr/serving/gate-scripts/serve-up.py``): gate 5 moves the earlier
wake's record aside and admits the second ``serve up`` of one host on one day.
Every switch that wakes a unit goes through the Waker.
"""

from __future__ import annotations

from pathlib import Path

from tests import onedoor
from tests.test_the_door_serves_a_ladder_and_leaves_it_up import (
    CONFIG_VAR,
    UNITS,
    compose_file,
    dev_config,
)


def test_a_second_serve_up_on_one_day_is_not_refused_for_the_first_ones_record(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    dev = dev_config(tmp_path / "dev.yaml")
    stubs = onedoor.stubs_dir(root)

    onedoor.serving(stubs, UNITS)
    first = onedoor.serve_door(
        root, "up", compose, suffix="wake-1", env_extra={CONFIG_VAR: str(dev)}
    )
    assert first.returncode == 0, first.stderr[-1500:]
    down = onedoor.serve_door(root, "down", compose, suffix="sleep-1")
    assert down.returncode == 0, down.stderr[-1500:]

    onedoor.serving(stubs, UNITS)
    again = onedoor.serve_door(
        root, "up", compose, suffix="wake-2", env_extra={CONFIG_VAR: str(dev)}
    )

    assert "already exists" not in again.stderr, (
        "the day's second wake was refused for the first wake's serve-up.json: "
        f"{again.stderr[-1500:]}"
    )
    assert again.returncode == 0, again.stderr[-1500:]
