"""A ``serve down`` removes every container of ours, not only those its file names.

RED, against code that exists. P0 of ``records/plans/fleet-identity.md`` §11,
and a prerequisite of live's auto-clean (§6).

The door runs every serve under one compose project (``-p mcgyvr``). The up
step already passes ``--remove-orphans``
(``src/mcgyvr/serving/gate-scripts/serve-up.py:58``); the down step does not
(``serve-down.py:29``), and ``docker compose down`` removes only the services
the file it is given defines
(https://docs.docker.com/reference/cli/docker/compose/down/). A dev ladder left
up under other service names survives a live down, and gate 2 then refuses the
next ``serve up`` on a rig that is not idle
(``src/mcgyvr/serving/gate-scripts/02-rig.py``).

The owner allowed either mechanism, a label-based removal or
``--remove-orphans`` (2026-09-10), so this reads the outcome: the container of
ours the file does not name is no longer on the daemon. The stub daemon removes
on ``down`` exactly what Docker's does (``tests/onedoor.py``).
"""

from __future__ import annotations

from pathlib import Path

from tests import onedoor
from tests.test_the_door_serves_a_ladder_and_leaves_it_up import UNITS, compose_file

#: A unit of ours a dev run left up under a service name this file does not have.
PLANTED = "mcgyvr-srv1-old-8009"


def test_serve_down_removes_a_container_of_ours_its_file_does_not_name(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    stubs = onedoor.stubs_dir(root)
    onedoor.serving(stubs, (*UNITS, PLANTED), already_up=True)

    result = onedoor.serve_door(root, "down", compose)

    listed = stubs / "serving-names"
    left = listed.read_text(encoding="utf-8").split() if listed.exists() else []
    assert not set(UNITS) & set(left), left
    assert PLANTED not in left, (
        f"serve down left {PLANTED}, a container of ours its file does not name, "
        f"on the daemon.\nstderr: {result.stderr[-1500:]}"
    )
