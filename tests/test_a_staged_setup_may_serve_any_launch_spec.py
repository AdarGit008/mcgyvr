"""A staged setup may serve any launch spec: the live ladder's, or its own.

Gate 1 (``src/mcgyvr/serving/gate-scripts/01-config.py``) admits a ``serve up``
and ``down`` under a setup ``mcgyvr setup`` staged in the data folder whatever
launch spec they name: nothing of it is locked yet, and setup starts and
samples it itself (:func:`mcgyvr.fleet.roots.runs_live`; owner ruling N11 in
``mcgyvr-lab/records/plans/sleep-wake.md``, that such a run runs everything;
the intent is ``mcgyvr-lab/records/plans/fleet-identity.md`` §6).

**Where the guard on a shared rig lives.** Every other run is held to the live
lock: gate 1 admits its ``serve up`` only for units the fleet lock names
(``tests/test_gate_1_admits_a_live_serve_up_only_from_the_fleet_lock.py``), and
live cleans units of ours the fleet does not name
(``tests/test_live_runs_only_a_locked_fleet_and_cleans_what_is_not_in_it.py``).

**Gate 2 is not widened.** Every run takes the rig's lease, a rig another
live run holds is refused, and a ``serve up`` onto a busy card is refused
(``tests/test_the_door_serves_a_ladder_and_leaves_it_up.py``).
"""

from __future__ import annotations

from pathlib import Path

from tests import onedoor
from tests.doors import UNITS, compose_file

CONFIG_VAR = "MCGYVR_CONFIG"

#: A ladder pointing at the fixture's rig, which is box1 under ``onedoor``.
LADDER = """\
units:
  only:
    address: http://box1:8001
    model: a-model
    rig: rig
    engine: vllm
ladder:
- only
sandbox:
  mode: tempdir
"""


def live_config(specs: Path) -> Path:
    """The live config, where the unnamed fallback looks for it.

    The live fleet ``~/.mcgyvr/live.json`` names, under the test's own HOME —
    every test in this suite runs in a HOME of its own (``tests/conftest.py``),
    so this writes a fixture and never the owner's install. One merged
    document stands in for the folder; the loader reads it the same way.
    """
    from mcgyvr.fleet.roots import fleets_dir, live_file

    path = fleets_dir() / "live-fixture"
    path.parent.mkdir(parents=True, exist_ok=True)
    live_file().write_text('{"fleet": "live-fixture"}', encoding="utf-8")
    path.write_text(LADDER + f"serving:\n  compose_dir: {specs}\n", encoding="utf-8")
    return path


def staged_config(root: Path) -> Path:
    """A setup ``mcgyvr setup`` staged: same rig, a folder of the data folder
    the fixture's door runs with (``onedoor.door_env``: ``root/data``)."""
    folder = root / "data" / "setup" / "20261015T000000-abcdef01"
    folder.mkdir(parents=True)
    path = folder / "setup.yaml"
    path.write_text(LADDER, encoding="utf-8")
    return path


def own_spec(root: Path, tmp_path: Path) -> Path:
    """A valid compose file that is not in the live config's ``compose_dir``."""
    mine = tmp_path / "mine"
    mine.mkdir()
    ours = compose_file(root)
    theirs = mine / ours.name
    theirs.write_text(ours.read_text(encoding="utf-8"), encoding="utf-8")
    return theirs


def _brought_up(root: Path, spec: Path) -> bool:
    return any(
        line.startswith(f"compose -f {spec} -p mcgyvr up -d")
        for line in onedoor.docker_log(root)
    )


def test_a_staged_setup_may_run_the_live_configs_own_launch_spec(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    live_config(root)
    staged = staged_config(root)
    onedoor.serving(onedoor.stubs_dir(root), UNITS, already_up=True)

    result = onedoor.serve_door(
        root, "down", compose, env_extra={CONFIG_VAR: str(staged)}
    )

    assert result.returncode == 0, (result.stdout, result.stderr[-1500:])


def test_a_staged_setup_may_bring_up_a_launch_spec_of_its_own(tmp_path: Path) -> None:
    """A spec outside the live ``compose_dir`` is admitted by gate 1."""
    root = onedoor.fixture_repo(tmp_path)
    live_config(root)
    theirs = own_spec(root, tmp_path)
    staged = staged_config(root)
    onedoor.serving(onedoor.stubs_dir(root), UNITS)

    result = onedoor.serve_door(root, "up", theirs, env_extra={CONFIG_VAR: str(staged)})

    assert "gate 1:" not in result.stderr, (
        "gate 1 refused a staged setup its own launch spec. The owner ruled "
        "that such a run runs everything, serve up and down included.\n"
        f"stderr: {result.stderr[-1500:]}"
    )
    assert result.returncode == 0, (result.stdout, result.stderr[-1500:])
    assert _brought_up(root, theirs), onedoor.docker_log(root)


def test_a_staged_setup_may_serve_when_no_live_ladder_is_configured(
    tmp_path: Path,
) -> None:
    """No live config at all: a staged setup needs no live ladder to serve
    its own."""
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    staged = staged_config(root)
    onedoor.serving(onedoor.stubs_dir(root), UNITS)

    result = onedoor.serve_door(
        root, "up", compose, env_extra={CONFIG_VAR: str(staged)}
    )

    assert "gate 1:" not in result.stderr, result.stderr[-1500:]
    assert result.returncode == 0, (result.stdout, result.stderr[-1500:])
    assert _brought_up(root, compose), onedoor.docker_log(root)
