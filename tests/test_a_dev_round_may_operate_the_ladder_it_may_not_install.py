"""A ``dev`` round may sleep and wake the live ladder; it may not install its own.

RED. Both tests fail today. Gate 1 (``src/mcgyvr/serving/gate-scripts/01-round.py``)
refuses ``serve up|down`` under a dev profile before any rig is read, and the
owner has overturned that: **``dev`` gets sleep and wake too.** The design is
``records/plans/sleep-wake.md`` §11.

**What the refusal was protecting, and what it over-collected.** Read against
its neighbours, gate 1's profile check guards two different things. The first is
composition: ``serve up`` starts whatever compose file it is handed, and a dev
config is by definition a setup under development — different models, a
different ``--gpu-memory-utilization``, a different image digest. Bring that up
on srv2 and every later live run measures against a ladder nobody declared. That
half is real. The second is availability, and it is already covered elsewhere:
gate 2 refuses a ``dev`` run any rig another run holds, and refuses *any* run —
dev or live — a rig that is not idle for ``serve up``. So the conflict gate 1
uniquely covers is the narrow one, a dev run acting on a card no other run
holds.

**The cut §11.2 proposes** keys on whose launch spec is being run rather than on
whose profile is running it:

    Under ``dev``, ``serve up|down`` is permitted only when ``RUN_COMPOSE`` names
    a file inside the live config's ``serving.compose_dir``, by ``emit_all``'s
    per-host naming convention — i.e. only when the spec being started or stopped
    is the live ladder's own. A dev run may **operate** the live ladder. It may
    never **install** one.

That keeps the composition guard whole: a dev config's freshly-emitted
``compose.srv2.yml`` sitting in the dev tree is not in the live ``compose_dir``
and is refused exactly as today, with today's message. It costs no rig time and
needs no scan — gate 1 already loads a config and already knows
``config.user_config_path()``, which it names in the very refusal being replaced.

**The residual, stated rather than hidden.** A dev run can now put the live
ladder to sleep on a free rig, which is the thing R1 was written to prevent. Its
price is bounded by this design's own machinery: the live run that arrives
afterwards finds the card asleep, is refused by the port, and wakes it, so it
pays one wake — 50 to 130 seconds — and not a failure, and the wake is in its own
envelope. Whether that price is acceptable is **N11** and is the owner's; the two
alternatives §11.3 offers are a direction-asymmetric dev (may wake, may not
sleep) and a lease-scoped dev sleep. This file pins the ruling, not N11's
resolution: it drives ``down``, which is the direction both alternatives would
still allow to be argued about, only through the case §11.2 permits.

Note that this contradicts, on purpose, the currently-green
``tests/red_port/test_dod_profile.py::test_a_dev_profile_does_not_touch_the_live_ladder``.
That test pins the refusal as a refusal *about the profile*. When the feature
lands it has to become a test about provenance, and this file is the statement of
what it becomes.
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
    a fixture and never the owner's install. It is the file gate 1 has to read
    to know which launch specs are the live ladder's.
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


def test_a_dev_round_may_run_the_live_configs_own_launch_spec(tmp_path: Path) -> None:
    """The ruling: a dev round operates the live ladder, and is not refused for it.

    The spec handed to the door is the one the live config's ``compose_dir``
    holds, so the composition on the rig stays the live config's whatever the
    running profile is. Nothing in R1's arbitration changes: gate 2 still makes a
    dev run yield a rig another run holds, and still refuses a ``serve up`` onto
    a busy card.

    ``down`` is the direction driven here because it is the one that carries the
    residual (§11.3): if a dev round may take the live ladder away, it may
    certainly bring it back.
    """
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    live_config(root)
    dev = dev_config(tmp_path / "dev.yaml")
    onedoor.serving(onedoor.stubs_dir(root), UNITS, already_up=True)

    result = onedoor.serve_door(root, "down", compose, env_extra={CONFIG_VAR: str(dev)})

    assert result.returncode == 0, (
        "a dev round was refused the live ladder's own launch spec. The owner "
        "overturned that refusal: dev gets sleep and wake too.\n"
        f"stdout: {result.stdout[-800:]}\nstderr: {result.stderr[-1500:]}"
    )


def test_a_dev_round_may_not_run_a_launch_spec_of_its_own(tmp_path: Path) -> None:
    """The half of the refusal that stays: a dev round may not *install* a ladder.

    The file below is a perfectly valid compose file that is simply not the live
    config's. Bringing it up would put units nobody declared on the shared rig,
    and every later live measurement would be against a ladder that was never
    reviewed — which is the composition guard, and it is the real one.

    The refusal has to be *about the spec*. A refusal that still only says "this
    run is under a dev profile" is the old rule wearing a new name: it would keep
    refusing the case above, and it tells an operator to change their profile
    when what is wrong is which file they pointed at.
    """
    root = onedoor.fixture_repo(tmp_path)
    live_config(root)
    mine = tmp_path / "mine"
    mine.mkdir()
    ours = compose_file(root)
    theirs = mine / ours.name
    theirs.write_text(ours.read_text(encoding="utf-8"), encoding="utf-8")
    dev = dev_config(tmp_path / "dev.yaml")
    onedoor.serving(onedoor.stubs_dir(root), UNITS)

    result = onedoor.serve_door(root, "up", theirs, env_extra={CONFIG_VAR: str(dev)})

    assert result.returncode == 2, (result.stdout, result.stderr[-1500:])
    assert onedoor.ssh_log(root) == [], "a rig was read before the refusal"
    assert str(theirs) in result.stderr, (
        "the refusal did not name the launch spec it refused. Gate 1 is still "
        "refusing the profile rather than the provenance, so it refuses a dev "
        "round the live ladder's own file too.\n"
        f"stderr: {result.stderr[-1500:]}"
    )
