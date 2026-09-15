"""A rig can be served down twice in one day.

``serve-up.py`` declares ``# RUN_REWRITES: serve-up.json``, so a second wake of
one host on one day supersedes the first wake's record
(``tests/test_a_card_can_be_woken_twice_in_one_day.py``). ``serve-down.py``
still declares ``# RUN_ARTIFACTS: serve-down.json``, and gate 5
(``src/mcgyvr/serving/gate-scripts/05-envelope.py``) refuses a write-once
artifact that already exists in ``records/evidence/<date>-live-<host>/``. A
suffix changes the RUN_ID and not the file name, so the day's second
``serve down`` of a host is refused before anything is stopped.

Found live on 2026-09-15: after b-small was brought up through the door, the
quick-check sweep's ``serve down --suffix qc`` on srv2 was refused with
"serve-down.json already exists under records/evidence/2026-09-15-live-srv2/",
and every later live cycle that day needed the earlier record moved aside by
hand. A live fleet that can be stopped through the door once a day cannot be
switched, slept or measured around.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests import onedoor
from tests.test_the_door_serves_a_ladder_and_leaves_it_up import (
    CONFIG_VAR,
    UNITS,
    compose_file,
    dev_config,
)


def test_a_second_serve_down_on_one_day_is_not_refused_for_the_first_ones_record(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    dev = dev_config(tmp_path / "dev.yaml")
    stubs = onedoor.stubs_dir(root)

    onedoor.serving(stubs, UNITS)
    up = onedoor.serve_door(
        root, "up", compose, suffix="wake-1", env_extra={CONFIG_VAR: str(dev)}
    )
    assert up.returncode == 0, up.stderr[-1500:]
    first = onedoor.serve_door(root, "down", compose, suffix="sleep-1")
    assert first.returncode == 0, first.stderr[-1500:]

    onedoor.serving(stubs, UNITS)
    again_up = onedoor.serve_door(
        root, "up", compose, suffix="wake-2", env_extra={CONFIG_VAR: str(dev)}
    )
    assert again_up.returncode == 0, again_up.stderr[-1500:]
    again = onedoor.serve_door(root, "down", compose, suffix="sleep-2")

    assert "already exists" not in again.stderr, (
        "the day's second serve down was refused for the first one's "
        f"serve-down.json: {again.stderr[-1500:]}"
    )
    assert again.returncode == 0, again.stderr[-1500:]


def test_the_first_serve_downs_record_is_kept_beside_the_second(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    stubs = onedoor.stubs_dir(root)

    onedoor.serving(stubs, UNITS, already_up=True)
    first = onedoor.serve_door(root, "down", compose, suffix="sleep-1")
    assert first.returncode == 0, first.stderr[-1500:]
    envelope = onedoor.envelope(root, "live-srv1")
    first_record = (envelope / "serve-down.json").read_bytes()
    first_run_id = json.loads(first_record)["run_id"]

    onedoor.serving(stubs, UNITS, already_up=True)
    again = onedoor.serve_door(root, "down", compose, suffix="sleep-2")
    assert again.returncode == 0, again.stderr[-1500:]

    kept = envelope / f"serve-down.superseded-{first_run_id}.json"
    assert kept.is_file(), sorted(p.name for p in envelope.iterdir())
    assert kept.read_bytes() == first_record, (
        "the first record was not kept byte for byte"
    )
    assert json.loads((envelope / "serve-down.json").read_text())["run_id"].endswith(
        "-sleep-2"
    )
