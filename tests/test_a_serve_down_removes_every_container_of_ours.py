"""A ``serve down`` removes every container of ours, not only those its file names.

The door runs every serve under one compose project (``-p mcgyvr``), and both
the up and the down step pass ``--remove-orphans``: ``docker compose down``
alone removes only the services the file it is given defines
(https://docs.docker.com/reference/cli/docker/compose/down/). A dev ladder left
up under other service names would survive such a down, and gate 2 refuses the
next ``serve up`` on a rig that is not idle
(``src/mcgyvr/serving/gate-scripts/02-rig.py``).

This reads the outcome and not the mechanism: the container of ours the file
does not name is not on the daemon after the down. The stub daemon removes on
``down`` exactly what Docker's does (``tests/onedoor.py``).
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
