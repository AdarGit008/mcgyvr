"""The rig is leased, and no run takes it from a live run that holds it.

A run that finds the
rig's lease held by a run that is still live — whichever door wrote it, the
product's or the lab's — is refused before it touches the rig, naming the
holder; it does not take the lease, and nothing of the holder's is torn down.
A lease whose holder is gone is stale and is reclaimed, so a run that crashed
does not lock a rig forever. R3: one fleet (box1, box2) is shared — mutual
exclusion, not partitioning.

Gate 5 claims the RUN_ID (``.<RUN_ID>.running`` in the envelope) so two
invocations of one step cannot run at once. That claim is per-envelope, so it does
not stop two different serve steps, or a laptop and box1, landing on one rig
together.
The contended resource is the rig, so there is a second claim there: a lease at
``~/.mcgyvr/lease`` on the rig itself, taken at gate 2 — before any rig time
is spent and before the envelope exists — and released on every way out.

What must be observably true:

* while a run is in progress the rig's lease names it (who holds it, from
  which pid, and since when), and when the run is over — finished, refused
  after gate 2, or interrupted — the lease is gone;
* a lease held by a live run refuses the new run at gate 2 in one line that
  names the holder's run and host and says to wait or end that run; the
  lease is left as it was, no container is listed or removed, the rig is not
  read, and nothing is filed;
* a lease is stale only when its holder is a pid on THIS machine that is
  gone — no process has that pid, or the process that has it now started at
  another time than the one the lease recorded (the pid was reused). A stale
  lease is named, not silently ignored, and reclaimed.

Every rig here is the stub behind the shims; the lease lives in the stub's
own home. Nothing reaches a machine.
"""

from __future__ import annotations

import contextlib
import getpass
import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests import onedoor
from tests.onedoor import Scenario

CONFIG_VAR = "MCGYVR_CONFIG"
FOLDER = "alpha"
RUN_ID = onedoor.run_id(Scenario(FOLDER, "1-probe.sh"))

SETUP_CONFIG = """\
units:
  only:
    address: http://localhost:8080
    model: a-model
    rig: local
ladder:
- only
sandbox:
  mode: tempdir
"""

#: Another operator's run, on another machine, holding the rig.
ELSEWHERE = "someone@elsewhere"
SINCE = "2026-09-06T01:02:03Z"
HOLDER_RUN = "2026-09-06-other-probe"
LEASE_ID = "deadbeefdeadbeef"


def _foreign(
    *,
    holder: str = ELSEWHERE,
    pid: int = 1,
    machine: str = "elsewhere0000",
    pid_start: str = "none",
    step: str = "probe",
    run_id: str = HOLDER_RUN,
) -> str:
    """A lease line as a door writes it, for a run that is not this one."""
    return (
        f"lease_id={LEASE_ID} holder={holder} "
        f"machine={machine} pid={pid} pid_start={pid_start} started_at={SINCE} "
        f"step={step} run_id={run_id}"
    )


def _machine() -> str:
    from mcgyvr.serving.gatelib import os_machine_id

    return os_machine_id()


def _me() -> str:
    return f"{getpass.getuser()}@{socket.gethostname()}"


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


def _started(pid: int) -> str:
    """When ``pid`` started, as the kernel says it (``/proc/<pid>/stat`` field
    22, clock ticks since boot): what tells one process from a later one that
    was given the same pid."""
    stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    return stat.rsplit(")", 1)[1].split()[19]


@contextlib.contextmanager
def _a_live_door(*door_argv: str) -> Iterator[subprocess.Popen[bytes]]:
    """A live process on this machine whose command line is a door's: what a
    run in progress is, as far as a lease's pid can tell."""
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(600)", *door_argv]
    )
    try:
        yield proc
    finally:
        proc.kill()
        proc.wait(timeout=30)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return onedoor.fixture_repo(tmp_path)


def _setup(tmp_path: Path) -> dict[str, str]:
    config = tmp_path / "setup.yaml"
    config.write_text(SETUP_CONFIG, encoding="utf-8")
    return {CONFIG_VAR: str(config)}


def _probe(root: Path, tmp_path: Path, after: str = "") -> Scenario:
    onedoor.add_step(
        root, FOLDER, "1-probe.sh", onedoor.probe_step(tmp_path / "e", after=after)
    )
    return Scenario(FOLDER, "1-probe.sh")


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
    for word in ("holder=", "pid=", "started_at="):
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
        proc.wait(timeout=90)
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        _, stderr = proc.communicate(timeout=60)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
    assert proc.returncode == 130, (proc.returncode, stderr)
    assert onedoor.read_lease(root) is None, "an interrupted run kept the lease"


# --- a live holder is never displaced -------------------------------------------

#: The door's own command lines, as a lease's pid would show them: the
#: product's (``python -m mcgyvr.serving.run``) and the lab's
#: (``tools/door/door.py``), which writes the same lease file in the same
#: format, with its run id from the start.
PRODUCT_DOOR = ("-m", "mcgyvr.serving.run", "serve", "up", "--host", "box1")
LAB_DOOR = ("tools/door/door.py", "--host", "box1", "--campaign", "c", "--step", "s")


def _refused_untouched(
    root: Path, tmp_path: Path, line: str, *, names: tuple[str, ...]
) -> str:
    """Run the door against a rig whose lease is ``line`` and a container up;
    assert it was refused at gate 2 with the rig untouched. Returns stderr."""
    onedoor.plant_lease(root, line)
    onedoor.containers_up(root, f"{HOLDER_RUN}-lcps")
    done = onedoor.door(root, _probe(root, tmp_path), env_extra=_setup(tmp_path))
    said = done.stdout + done.stderr
    assert done.returncode == 2, (done.returncode, said[-1500:])
    refusal = [ln for ln in done.stderr.splitlines() if "is held by" in ln]
    assert len(refusal) == 1, said
    for name in names:
        assert name in refusal[0], (name, refusal[0])
    assert "wait" in refusal[0].lower(), refusal[0]
    assert "stale" not in said, said
    assert onedoor.read_lease(root) == line + "\n", "the holder's lease was touched"
    assert onedoor.docker_log(root) == [], "the holder's daemon was reached"
    assert all(entry.endswith("bash -s -- lease") for entry in onedoor.ssh_log(root)), (
        f"the rig was reached beyond its lease: {onedoor.ssh_log(root)}"
    )
    assert not (tmp_path / "e").exists(), "the step ran on a held rig"
    assert onedoor.written_under_records(root) == [], "a refused run filed"
    return done.stderr


def test_a_lease_a_run_on_another_machine_holds_refuses_this_run(
    root: Path, tmp_path: Path
) -> None:
    """Another operator's run, from another machine: its pid cannot be asked
    from here, so it is live. This run is refused, naming that run and its
    host, and nothing of it is touched."""
    _refused_untouched(root, tmp_path, _foreign(), names=(HOLDER_RUN, "elsewhere"))


def test_a_lease_whose_run_has_minted_no_id_yet_refuses_this_run(
    root: Path, tmp_path: Path
) -> None:
    """A product run between gate 2 and gate 5 holds a lease with no run id."""
    line = _foreign(step="serve-up", run_id="none")
    _refused_untouched(root, tmp_path, line, names=("serve-up", "elsewhere"))


@pytest.mark.parametrize("door_argv", [PRODUCT_DOOR, LAB_DOOR], ids=["product", "lab"])
def test_a_live_door_on_this_machine_holds_its_lease_whichever_door_it_is(
    root: Path, tmp_path: Path, door_argv: tuple[str, ...]
) -> None:
    """A door on THIS machine is still running and holds the rig. Whether it
    is the product's door or the lab's, its pid is alive and is the very
    process that took the lease: live, so this run is refused."""
    with _a_live_door(*door_argv) as holder:
        line = _foreign(
            holder=_me(),
            pid=holder.pid,
            machine=_machine(),
            pid_start=_started(holder.pid),
        )
        _refused_untouched(
            root, tmp_path, line, names=(HOLDER_RUN, socket.gethostname())
        )


def test_a_lease_the_door_did_not_write_is_honoured(root: Path, tmp_path: Path) -> None:
    """No lease_id on the line — a hand-written lease, or an older door's.
    Something holds the rig and nothing says it is gone: refused, untouched."""
    line = f"holder={ELSEWHERE} pid=1 started_at={SINCE} step=probe run_id={HOLDER_RUN}"
    _refused_untouched(root, tmp_path, line, names=(HOLDER_RUN, "elsewhere"))


def test_a_dead_pid_on_a_machine_with_this_hostname_but_another_id_is_honoured(
    root: Path, tmp_path: Path
) -> None:
    """Two machines named alike: a dead pid here says nothing about a run
    there. Not stale, and not taken."""
    line = _foreign(holder=_me(), pid=_dead_pid())
    _refused_untouched(root, tmp_path, line, names=(HOLDER_RUN,))


# --- a stale lease ---------------------------------------------------------------


def test_a_stale_lease_is_named_and_reclaimed(root: Path, tmp_path: Path) -> None:
    """The holder is a pid on THIS machine that is gone: the lease is stale.
    Named — an operator should know a run died without releasing — and
    reclaimed, because a dead run holds nothing. Nothing of it is torn down."""
    onedoor.plant_lease(
        root, _foreign(holder=_me(), pid=_dead_pid(), machine=_machine())
    )
    onedoor.containers_up(root, f"{HOLDER_RUN}-lcps")
    done = onedoor.door(root, _probe(root, tmp_path), env_extra=_setup(tmp_path))
    said = done.stdout + done.stderr
    assert "stale" in said, said
    assert (tmp_path / "e").exists(), f"the step did not run: {said[-1500:]}"
    removed = [line for line in onedoor.docker_log(root) if line.startswith("rm")]
    assert removed == [], f"a stale run's containers were torn down: {removed}"
    assert onedoor.read_lease(root) is None


def test_a_pid_that_another_process_has_since_taken_is_stale(
    root: Path, tmp_path: Path
) -> None:
    """The holder's pid is alive, but the process that has it started at
    another time than the lease recorded: the run died and its pid was
    reused. Alive is not enough; it must be the same process."""
    with _a_live_door(*PRODUCT_DOOR) as other:
        reused = str(int(_started(other.pid)) + 1)
        line = _foreign(
            holder=_me(), pid=other.pid, machine=_machine(), pid_start=reused
        )
        onedoor.plant_lease(root, line)
        done = onedoor.door(root, _probe(root, tmp_path), env_extra=_setup(tmp_path))
    assert done.returncode == 0, done.stderr[-1500:]
    assert "stale" in done.stderr, done.stderr
    assert onedoor.read_lease(root) is None


def test_an_empty_lease_file_holds_nothing(root: Path, tmp_path: Path) -> None:
    """A write that never finished leaves a zero-byte file. Noclobber would
    refuse to write over it and no operator is named to wait for: it holds
    nothing, and a run takes the rig."""
    onedoor.plant_lease(root, "")
    done = onedoor.door(root, _probe(root, tmp_path), env_extra=_setup(tmp_path))
    assert done.returncode == 0, done.stderr[-1500:]
    assert onedoor.read_lease(root) is None


def test_a_lease_names_the_start_of_the_process_that_holds_it() -> None:
    """What the staleness rule reads back is written by every door: the
    holder's pid and the kernel's start time of that very process."""
    from mcgyvr.serving.gatelib import Lease, new_lease

    lease = new_lease("probe", os.getpid())
    assert lease.pid_start == _started(os.getpid())
    parsed = Lease.parse(lease.line())
    assert parsed is not None and parsed.pid_start == lease.pid_start
    assert not parsed.is_stale(), "this very process read as gone"
