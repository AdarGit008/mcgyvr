"""A signal to the door ends the step — through its own cleanup — before gate 7.

Gate 7 re-reads the rig and lists the daemon's containers on the premise that
the step is over; a step still running under it makes both readings lies. The
door ends the entry that was running before it moves on (``run.py:_end``),
but the entry is ``06-step.py`` and not the step: a ``kill`` of the door alone
used to end that Python wrapper at once and leave the step itself, reparented,
still running while gate 7 read the rig. A terminal's Ctrl-C reaches the step
directly, but the wrapper answered its own copy with a SIGKILL of the step a
quarter second later, racing the step's INT/TERM trap — the trap that removes
the container it had started (``default-step.sh``, ``$CURRENT``).

So whatever the signal and however it is delivered, the step gets it once,
runs its trap to the end, and is gone before gate 7's first ``docker ps``.
"""

from __future__ import annotations

import contextlib
import os
import signal
import time
from pathlib import Path

import pytest

from tests import onedoor
from tests.onedoor import Scenario

PROBE = Scenario("alpha", "1-probe.sh")


def _trapping_step(tmp_path: Path, docker_log: Path) -> str:
    """The probe step, then a wait on a long sleep under a TERM/INT trap that
    takes a second to clean up and records how far docker's log had got."""
    after = (
        f"printf '%s' \"$$\" > '{tmp_path / 'step-pid'}'\n"
        "trap 'sleep 1; "
        f'wc -l < "{docker_log}" > "{tmp_path / "cleaned"}"; '
        'kill "$nap" 2>/dev/null; exit 143\' TERM INT\n'
        "sleep 120 &\n"
        "nap=$!\n"
        f"printf '%s' \"$nap\" > '{tmp_path / 'nap-pid'}'\n"
        f"touch '{tmp_path / 'step-ran'}'\n"
        'wait "$nap"\n'
    )
    return onedoor.probe_step(tmp_path / "e", after=after)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie is gone for this purpose: it runs nothing.
    with contextlib.suppress(OSError):
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        return stat.rsplit(")", 1)[1].split()[0] != "Z"
    return False


@pytest.mark.parametrize(
    ("sig", "whole_group"),
    [(signal.SIGTERM, False), (signal.SIGINT, True)],
    ids=["kill-the-door", "ctrl-c"],
)
def test_the_step_has_run_its_trap_and_is_gone_before_gate_7(
    tmp_path: Path, sig: signal.Signals, whole_group: bool
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    docker_log = onedoor.stubs_dir(root) / "docker.log"
    onedoor.add_step(root, "alpha", "1-probe.sh", _trapping_step(tmp_path, docker_log))

    proc = onedoor.door_process(root, PROBE)
    pids: list[int] = []
    try:
        deadline = time.monotonic() + 120
        while not (tmp_path / "step-ran").exists():
            assert proc.poll() is None, proc.communicate()
            assert time.monotonic() < deadline, "the step never reached its wait"
            time.sleep(0.1)
        pids = [
            int((tmp_path / name).read_text(encoding="utf-8"))
            for name in ("step-pid", "nap-pid")
        ]
        if whole_group:
            os.killpg(proc.pid, sig)
        else:
            os.kill(proc.pid, sig)
        proc.wait(timeout=90)
        still = [pid for pid in pids if _alive(pid)]
    finally:
        for pid in pids:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
    _, stderr = proc.communicate(timeout=60)

    assert proc.returncode == 130, (proc.returncode, stderr[-1500:])
    assert still == [], (
        f"the step outlived the door: {still} still running.\n{stderr[-1500:]}"
    )
    cleaned = tmp_path / "cleaned"
    assert cleaned.exists(), (
        f"the step's own trap never finished its cleanup.\n{stderr[-1500:]}"
    )
    seen = int(cleaned.read_text(encoding="utf-8").strip())
    log = docker_log.read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("ps") for line in log[seen:]), (
        f"gate 7 listed the daemon before the step's cleanup was over: {log[:seen]}"
    )
