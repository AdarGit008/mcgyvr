"""The ALWAYS phase is signal-safe: gates 7 and 8 complete whatever arrives.

A step that had left a container found the door's pid in ``/proc`` (its own
ancestor chain, the way ``gatelib.under_door`` reads it), left a detached
process behind, and had it ``kill -INT`` the door while gate 7 was inside
``docker ps``. The door's ``_run_entry`` was in ``pipe.read()``; the
``KeyboardInterrupt`` escaped ``main`` as a traceback, gate 7's finding was
never printed, gate 8 never ran, and the claim on the RUN_ID was never
released. A run whose end state is unknown is exactly the one that ended
silently — and this one was made to.

So ``run.py`` ignores SIGINT and SIGTERM (``signal.SIG_IGN``) for the whole
of the ALWAYS phase and restores them after: 7 and 8 always complete. The
exit code is 130 when an interrupt landed earlier (before or during the
step, where it is handled), else what 7 and 8 decided. Here the interrupt
lands during gate 7, so the exit is gate 7's 1 — the leftover, named — and
gate 8's line follows it.
"""

from __future__ import annotations

import time
from pathlib import Path

from tests import onedoor
from tests.onedoor import Scenario

PROBE = Scenario("alpha", "1-probe.sh")

#: How long the docker stub holds ``ps``: long enough for the killer to see
#: the call in the log and signal the door while gate 7 is still inside it.
PS_SLEEP = 3.0


def _killer_step(env_file: Path, tmp_path: Path, docker_log: Path) -> str:
    """The probe step, plus: find the door in /proc, leave a detached killer
    that waits for gate 7's ``docker ps`` in the stub's log and INTs the door."""
    flag = tmp_path / "step-ran"
    find_door = (
        "pid=$$; door=\n"
        'while [ "$pid" -gt 1 ]; do\n'
        "  if tr '\\0' ' ' < /proc/$pid/cmdline 2>/dev/null | "
        "grep -q 'mcgyvr/serving/run.py'; then door=$pid; break; fi\n"
        "  pid=$(sed 's/.*) //' /proc/$pid/stat | awk '{print $2}')\n"
        "done\n"
        '[ -n "$door" ] || { echo "probe: no door in /proc" >&2; exit 3; }\n'
        f"printf '%s' \"$door\" > '{tmp_path / 'door-pid'}'\n"
        f"touch '{flag}'\n"
        # Detached: its own session, no inherited stdio, so the door's pipes
        # close when the step exits and the killer outlives gate 6.
        "setsid bash -c '"
        'while ! grep -q "^ps" "$1" 2>/dev/null; do sleep 0.05; done; '
        'kill -INT "$2"; touch "$3"'
        f"' _ '{docker_log}' \"$door\" '{tmp_path / 'kill-sent'}' "
        ">/dev/null 2>&1 </dev/null &\n"
        "disown\n"
    )
    return onedoor.probe_step(env_file, after=find_door)


def test_an_interrupt_delivered_during_gate_7_leaves_7_and_8_to_finish(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    stubs = onedoor.stubs_dir(root)
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        _killer_step(tmp_path / "e", tmp_path, stubs / "docker.log"),
    )
    flag = tmp_path / "step-ran"
    onedoor.docker_stub(stubs, leftover_flag=flag, ps_sleep=PS_SLEEP)

    proc = onedoor.door_process(root, PROBE)
    try:
        stdout, stderr = proc.communicate(timeout=300)
    finally:
        if proc.poll() is None:
            proc.kill()
    kill_sent = tmp_path / "kill-sent"
    assert kill_sent.exists(), (
        "the step's killer never fired, so nothing was tested",
        stdout,
        stderr,
    )
    assert int((tmp_path / "door-pid").read_text(encoding="utf-8")) == proc.pid, (
        "the step did not find the door in /proc"
    )
    assert "Traceback" not in stderr, stderr
    assert proc.returncode == 1, (proc.returncode, stdout, stderr)
    run_id = onedoor.read_env_file(tmp_path / "e")["RUN_ID"]
    assert f"named for this run: {run_id}-lcps" in stderr, (
        f"gate 7 did not finish and name the leftover: {stderr}"
    )
    assert "1 artifact(s) parse" in stdout, f"gate 8 did not run: {stdout} {stderr}"
    assert "interrupted" not in stderr, (
        "an interrupt during gate 7 is not one before it"
    )
    assert onedoor.claims(root) == [], "the claim on the RUN_ID was not released"


def test_an_interrupt_before_gate_7_still_exits_130_and_releases_the_claim(
    tmp_path: Path,
) -> None:
    """The other exit code: the interrupt lands in the step, where it is
    handled; 7 and 8 run, the door exits 130, and the claim is gone."""
    import os
    import signal

    root = onedoor.fixture_repo(tmp_path)
    flag = tmp_path / "step-ran"
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        onedoor.probe_step(tmp_path / "e", after=f"touch '{flag}'\nsleep 120"),
    )
    proc = onedoor.door_process(root, PROBE)
    try:
        deadline = time.monotonic() + 120
        while not flag.exists():
            assert proc.poll() is None, proc.communicate()
            assert time.monotonic() < deadline, "the step never reached its hang"
            time.sleep(0.1)
        run_id = onedoor.read_env_file(tmp_path / "e")["RUN_ID"]
        assert (onedoor.envelope(root, "alpha") / f".{run_id}.running").is_file()
        os.killpg(proc.pid, signal.SIGINT)
        stdout, stderr = proc.communicate(timeout=120)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
    assert proc.returncode == 130, (proc.returncode, stderr)
    assert "1 artifact(s) parse" in stdout, (stdout, stderr)
    assert onedoor.claims(root) == [], "an interrupted run kept its claim"
