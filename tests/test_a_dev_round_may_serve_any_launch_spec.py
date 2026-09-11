"""A ``dev`` round may serve any launch spec: the live ladder's, or its own.

RED for the second and third tests. Gate 1
(``src/mcgyvr/serving/gate-scripts/01-round.py:112``) lets a dev round operate
only a spec inside the live config's ``serving.compose_dir`` and refuses any
other before a rig is read. The owner widened sleep-wake §11.2 on 2026-09-10:
**dev runs everything, ``serve up`` and ``down`` included** — N11 is ruled. The
intent is ``records/plans/fleet-identity.md`` §6.

**What the refused half protected, and where that went.** The composition guard
kept a ladder nobody declared off a shared rig, so that every later live run did
not measure against it. Live is now production and runs only a locked fleet:
gate 1 admits a live ``serve up`` only for units the fleet lock names
(``tests/test_gate_1_admits_a_live_serve_up_only_from_the_fleet_lock.py``), and
live cleans units of ours the fleet does not name
(``tests/test_live_runs_only_a_locked_fleet_and_cleans_what_is_not_in_it.py``).
Guarding dev at gate 1 as well would be the same rule in a second place.

**What does not change.** Gate 2 still makes a dev run yield a rig another run
holds, and still refuses a ``serve up`` onto a busy card
(``tests/test_the_door_serves_a_ladder_and_leaves_it_up.py``).

This replaces ``tests/test_a_dev_round_may_operate_the_ladder_it_may_not_install.py``,
whose second test pinned the refusal, and
``tests/red_port/test_dod_profile.py::test_a_dev_profile_does_not_touch_the_live_ladder``
and ``::test_a_dev_serve_refused_at_gate_1_leaves_even_the_rounds_file_alone``.
"""

from __future__ import annotations

from pathlib import Path

from tests import onedoor
from tests.test_the_door_serves_a_ladder_and_leaves_it_up import UNITS, compose_file

CONFIG_VAR = "MCGYVR_CONFIG"

#: A ladder pointing at the fixture's rig, which is srv1 under ``onedoor``.
LADDER = """
version: 1
sources:
  rig:
    base_url: "http://srv1:8001"
    api: openai
    engine: vllm
    max_parallel: 1
ladder:
  tiers:
    - name: only
      source: rig
      model: "a-model"
sandbox:
  mode: tempdir
"""


def live_config(specs: Path) -> Path:
    """The live config, where the unnamed fallback looks for it.

    ``~/.mcgyvr/config/mcgyvr.yaml`` under the test's own HOME — every test in
    this suite runs in a HOME of its own (``tests/conftest.py``), so this writes
    a fixture and never the owner's install.
    """
    from mcgyvr.config import user_config_path

    path = user_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(LADDER + f"serving:\n  compose_dir: {specs}\n", encoding="utf-8")
    return path


def dev_config(path: Path) -> Path:
    """A setup under development: same rig, its own file, ``profile: dev``."""
    path.write_text("profile: dev\n" + LADDER, encoding="utf-8")
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


def test_a_dev_round_may_run_the_live_configs_own_launch_spec(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    live_config(root)
    dev = dev_config(tmp_path / "dev.yaml")
    onedoor.serving(onedoor.stubs_dir(root), UNITS, already_up=True)

    result = onedoor.serve_door(root, "down", compose, env_extra={CONFIG_VAR: str(dev)})

    assert result.returncode == 0, (result.stdout, result.stderr[-1500:])


def test_a_dev_round_may_bring_up_a_launch_spec_of_its_own(tmp_path: Path) -> None:
    """The case gate 1 refuses today: a dev spec outside the live ``compose_dir``."""
    root = onedoor.fixture_repo(tmp_path)
    live_config(root)
    theirs = own_spec(root, tmp_path)
    dev = dev_config(tmp_path / "dev.yaml")
    onedoor.serving(onedoor.stubs_dir(root), UNITS)

    result = onedoor.serve_door(root, "up", theirs, env_extra={CONFIG_VAR: str(dev)})

    assert "gate 1:" not in result.stderr, (
        "gate 1 refused a dev round its own launch spec. The owner ruled on "
        "2026-09-10 that dev runs everything, serve up and down included.\n"
        f"stderr: {result.stderr[-1500:]}"
    )
    assert result.returncode == 0, (result.stdout, result.stderr[-1500:])
    assert _brought_up(root, theirs), onedoor.docker_log(root)


def test_a_dev_round_may_serve_when_no_live_ladder_is_configured(
    tmp_path: Path,
) -> None:
    """No live config at all: gate 1 refuses today because there is "no live
    ladder to operate". A dev round needs none to serve its own."""
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    dev = dev_config(tmp_path / "dev.yaml")
    onedoor.serving(onedoor.stubs_dir(root), UNITS)

    result = onedoor.serve_door(root, "up", compose, env_extra={CONFIG_VAR: str(dev)})

    assert "gate 1:" not in result.stderr, result.stderr[-1500:]
    assert result.returncode == 0, (result.stdout, result.stderr[-1500:])
    assert _brought_up(root, compose), onedoor.docker_log(root)
