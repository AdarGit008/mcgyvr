"""``serve up`` records how many times each unit restarted.

The one place a unit's start is recorded is ``serve-up.json``, and its rows are
what ``servelib.wait_for`` returns: container, port, healthy, sleeping,
seconds, models and ``restarts``.
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


def test_serve_up_files_a_restart_count_for_every_unit(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    dev = dev_config(tmp_path / "dev.yaml")
    onedoor.serving(onedoor.stubs_dir(root), UNITS)

    result = onedoor.serve_door(root, "up", compose, env_extra={CONFIG_VAR: str(dev)})
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
