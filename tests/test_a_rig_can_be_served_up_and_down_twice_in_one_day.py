"""A rig can be served up and down twice in one day.

The Waker gives every wake a RUN_ID of its own (``--suffix``,
``mcgyvr.wake``), and ``serve-up.py`` and ``serve-down.py`` declare their
records as ones they may write again (``# RUN_REWRITES: serve-up.json`` /
``serve-down.json``), so gate 5 (``src/mcgyvr/serving/gate-scripts/
05-envelope.py``) never refuses the day's second ``serve up`` or ``serve
down`` of a host for the first one's record. A live fleet that can be woken
or stopped through the door once a day cannot be switched or slept.
"""

from __future__ import annotations

from pathlib import Path

from tests import onedoor
from tests.doors import CONFIG_VAR, UNITS, compose_file, dev_config


def test_a_second_serve_up_and_down_on_one_day_are_not_refused_for_the_first_records(
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
    down = onedoor.serve_door(root, "down", compose, suffix="sleep-1")
    assert down.returncode == 0, down.stderr[-1500:]

    onedoor.serving(stubs, UNITS)
    again_up = onedoor.serve_door(
        root, "up", compose, suffix="wake-2", env_extra={CONFIG_VAR: str(dev)}
    )
    assert "already exists" not in again_up.stderr, (
        "the day's second wake was refused for the first wake's serve-up.json: "
        f"{again_up.stderr[-1500:]}"
    )
    assert again_up.returncode == 0, again_up.stderr[-1500:]
    again_down = onedoor.serve_door(root, "down", compose, suffix="sleep-2")

    assert "already exists" not in again_down.stderr, (
        "the day's second serve down was refused for the first one's "
        f"serve-down.json: {again_down.stderr[-1500:]}"
    )
    assert again_down.returncode == 0, again_down.stderr[-1500:]
