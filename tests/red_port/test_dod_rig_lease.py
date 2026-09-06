"""The rig is leased, live outranks dev, and dev yields — enforced by the machine.

Owner's rulings (2026-09-06). R1: a live run preempts a dev run, dev yields,
and the machine enforces it rather than a convention. R3: dev and prod share
one fleet (srv1, srv2) — mutual exclusion, not partitioning.

Gate 5 already claims the RUN_ID (``.<RUN_ID>.running`` in the envelope) so two
invocations of one step cannot run at once. That claim is per-envelope, so two
different steps, or a laptop and srv1, can still land on one rig together. The
contended resource is the rig, so the claim moves there: a lease at
``~/.mcgyvr/lease`` on the rig itself, taken at gate 2 — before any rig time
is spent and before the envelope exists — and released on every way out.

What must be observably true:

* while a run is in progress the rig's lease names it (its profile, who holds
  it, from which pid, and since when), and when the run is over — finished,
  refused after gate 2, or interrupted — the lease is gone;
* a ``dev`` run against a rig whose lease is held is refused at gate 2, naming
  the holder and when the lease was taken, and touches nothing;
* a ``live`` run takes the lease whatever holds it, names what it displaced,
  and tears down the displaced run's containers — at gate 2, so its own step
  runs on an idle rig, and again at gate 7 for anything that came back;
* a lease whose holder is a pid on this machine that is gone is stale: it is
  named, not silently ignored, and taken over;
* a dev run whose lease was taken from it under its feet yields: its next
  touch of the rig through the door's shims is refused naming the new holder,
  and it does not release a lease that is no longer its own.

Every rig here is the stub behind the shims; the lease lives in the stub's
own home. Nothing reaches a machine.
"""

from __future__ import annotations

import getpass
import os
import signal
import socket
import time
from pathlib import Path

import pytest

from tests import onedoor
from tests.onedoor import Scenario

CONFIG_VAR = "MCGYVR_CONFIG"
CAMPAIGN = "alpha"
RUN_ID = f"{onedoor.RUN_DATE}-{CAMPAIGN}-probe"

DEV_CONFIG = """\
profile: dev
version: 1
sources:
  local:
    base_url: "http://localhost:8080"
    api: openai
    max_parallel: 1
ladder:
  tiers:
    - name: only
      source: local
      model: "a-model"
sandbox:
  mode: tempdir
"""

#: Another operator's run, on another machine, holding the rig.
ELSEWHERE = "someone@elsewhere"
SINCE = "2026-09-06T01:02:03Z"
DISPLACED_RUN = "2026-09-06-other-probe"


def _foreign(profile: str, *, holder: str = ELSEWHERE, pid: int = 1) -> str:
    return (
        f"lease_id=deadbeefdeadbeef profile={profile} holder={holder} pid={pid} "
        f"started_at={SINCE} campaign=other step=probe run_id={DISPLACED_RUN}"
    )


def _dead_pid() -> int:
    """A pid nothing on this machine has."""
    candidate = 4_000_000
    while True:
        try:
            os.kill(candidate, 0)
        except ProcessLookupError:
            return candidate
        except PermissionError:
            pass
        candidate -= 1


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return onedoor.fixture_repo(tmp_path)


def _dev(tmp_path: Path) -> dict[str, str]:
    config = tmp_path / "dev.yaml"
    config.write_text(DEV_CONFIG, encoding="utf-8")
    return {CONFIG_VAR: str(config)}


def _probe(root: Path, tmp_path: Path, after: str = "") -> Scenario:
    onedoor.add_step(
        root, CAMPAIGN, "1-probe.sh", onedoor.probe_step(tmp_path / "e", after=after)
    )
    return Scenario(CAMPAIGN, "1-probe.sh")


# --- taking and releasing ----------------------------------------------------


def test_a_run_holds_the_lease_while_it_runs_and_releases_it_after(
    root: Path, tmp_path: Path
) -> None:
    during = tmp_path / "lease-during.txt"
    # The step asks the rig — through the door's ssh shim — what the lease
    # says while the step is running.
    after = f"ssh \"$RUN_HOST\" 'cat ~/.mcgyvr/lease' > '{during}'\n"
    done = onedoor.door(root, _probe(root, tmp_path, after))
    assert done.returncode == 0, done.stderr[-1500:]
    held = during.read_text(encoding="utf-8")
    for word in ("profile=live", "holder=", "pid=", "started_at="):
        assert word in held, held
    assert getpass.getuser() in held and socket.gethostname() in held, held
    assert onedoor.read_lease(root) is None, "the lease outlived the run"


def test_the_lease_is_released_when_a_later_gate_refuses(
    root: Path, tmp_path: Path
) -> None:
    """Gate 3 refuses (no daemon behind the CLI) after gate 2 took the lease."""
    onedoor.docker_stub(onedoor.stubs_dir(root), daemon_down=True)
    done = onedoor.door(root, _probe(root, tmp_path))
    assert done.returncode == 2, (done.returncode, done.stderr[-1500:])
    assert onedoor.read_lease(root) is None, "a refused run kept the lease"


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM], ids=["INT", "TERM"])
def test_the_lease_is_released_on_an_interrupt(
    root: Path, tmp_path: Path, sig: signal.Signals
) -> None:
    flag = tmp_path / "step-ran"
    scenario = _probe(root, tmp_path, after=f"touch '{flag}'\nsleep 120")
    proc = onedoor.door_process(root, scenario)
    try:
        deadline = time.monotonic() + 120
        while not flag.exists():
            assert proc.poll() is None, proc.communicate()
            assert time.monotonic() < deadline, "the step never reached its hang"
            time.sleep(0.1)
        assert onedoor.read_lease(root) is not None, "no lease during the step"
        os.killpg(proc.pid, sig)
        _, stderr = proc.communicate(timeout=120)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
    assert proc.returncode == 130, (proc.returncode, stderr)
    assert onedoor.read_lease(root) is None, "an interrupted run kept the lease"


# --- dev against a held rig -----------------------------------------------------


def test_a_dev_run_refuses_a_held_rig_naming_the_holder_and_when(
    root: Path, tmp_path: Path
) -> None:
    planted = onedoor.plant_lease(root, _foreign("live"))
    before = planted.read_text(encoding="utf-8")
    done = onedoor.door(root, _probe(root, tmp_path), env_extra=_dev(tmp_path))
    assert done.returncode == 2, (done.returncode, done.stderr[-1500:])
    assert ELSEWHERE in done.stderr and SINCE in done.stderr, done.stderr
    assert planted.read_text(encoding="utf-8") == before, "the refusal moved the lease"
    assert onedoor.written_under_records(root) == [], "a refused run wrote"
    assert not (tmp_path / "e").exists(), "the step ran on a held rig"


def test_a_stale_lease_is_named_and_taken_over(root: Path, tmp_path: Path) -> None:
    """The holder is a pid on THIS machine that is gone: the lease is stale.
    Named — an operator should know a run died without releasing — and taken,
    because a dead run holds nothing."""
    me = f"{getpass.getuser()}@{socket.gethostname()}"
    onedoor.plant_lease(root, _foreign("dev", holder=me, pid=_dead_pid()))
    done = onedoor.door(root, _probe(root, tmp_path), env_extra=_dev(tmp_path))
    assert done.returncode == 0, done.stderr[-1500:]
    assert "stale" in (done.stdout + done.stderr), done.stdout + done.stderr
    assert onedoor.read_lease(root) is None


# --- live displaces dev ---------------------------------------------------------


def test_a_live_run_takes_a_held_lease_and_tears_down_what_it_displaced(
    root: Path, tmp_path: Path
) -> None:
    """A dev run holds the rig and its container is up. A live run (no config
    named: live is the default) takes the lease, names what it displaced,
    removes the displaced run's container by name — so its own step opens
    on an idle rig — and is green."""
    onedoor.plant_lease(root, _foreign("dev"))
    onedoor.containers_up(root, f"{DISPLACED_RUN}-lcps")
    done = onedoor.door(root, _probe(root, tmp_path))
    said = done.stdout + done.stderr
    assert done.returncode == 0, done.stderr[-1500:]
    assert ELSEWHERE in said, said
    removed = [
        line
        for line in onedoor.docker_log(root)
        if line.startswith("rm") and f"{DISPLACED_RUN}-lcps" in line
    ]
    assert removed, onedoor.docker_log(root)
    assert onedoor.read_lease(root) is None


def test_gate_7_tears_down_a_displaced_run_that_came_back_during_the_step(
    root: Path, tmp_path: Path
) -> None:
    """The displaced dev step retries its launch after gate 2 removed its
    container; gate 7 finds it up after the step and removes it again, by
    the name the lease gave it, and the live run is still green."""
    onedoor.plant_lease(root, _foreign("dev"))
    onedoor.containers_up(root, f"{DISPLACED_RUN}-lcps")
    names = onedoor.stubs_dir(root) / "serving-names"
    came_back = f"printf '%s\\n' '{DISPLACED_RUN}-lcps' >> '{names}'\n"
    done = onedoor.door(root, _probe(root, tmp_path, after=came_back))
    assert done.returncode == 0, done.stderr[-1500:]
    removed = [
        line
        for line in onedoor.docker_log(root)
        if line.startswith("rm") and f"{DISPLACED_RUN}-lcps" in line
    ]
    assert len(removed) >= 2, onedoor.docker_log(root)
    assert names.read_text(encoding="utf-8").strip() == "", "the container is up"


# --- dev yields ------------------------------------------------------------------


def test_a_dev_run_whose_lease_was_taken_yields_at_its_next_touch_of_the_rig(
    root: Path, tmp_path: Path
) -> None:
    """Mid-step, a live run takes the rig (the lease is overwritten under the
    dev run). The dev step's next `docker run` through the shim is refused
    naming the new holder, the step fails, the run is not green, and the
    lease — no longer this run's — is left as the live run wrote it."""
    taken = _foreign("live")
    lease = onedoor.rig_lease(root)
    after = (
        f"printf '%s\\n' '{taken}' > '{lease}'\n"
        "docker run --name probe-x some/image:tag\n"
    )
    done = onedoor.door(root, _probe(root, tmp_path, after), env_extra=_dev(tmp_path))
    assert done.returncode != 0, "the dev run went on under someone else's lease"
    assert ELSEWHERE in done.stderr, done.stderr
    launches = [line for line in onedoor.docker_log(root) if line.startswith("run ")]
    assert launches == [], f"the launch reached the daemon: {launches}"
    assert onedoor.read_lease(root) == taken + "\n", onedoor.read_lease(root)
