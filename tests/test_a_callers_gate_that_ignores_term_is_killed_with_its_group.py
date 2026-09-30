"""A caller's gate that ignores TERM is killed with its process group.

The door ends a caller's gate by sending its process group TERM, and KILL
when the group is still there after a grace; then it waits for the group to
be empty before it goes on. A gate and a child of it that both ignore TERM
are killed all the same: at the gate's bound, on one signal to the door, on
a second signal that arrives while the door waits out the grace, and on two
signals that arrive back to back, in each phase a gate runs in. Both are
gone before the lease is released, or before the door exits when no lease
was taken yet: also when a signal arrives after KILL, while the door waits
for the group to be empty, and when the door itself adopts the processes
orphaned below it.
"""

from __future__ import annotations

import os
import re
import signal
import time
from pathlib import Path

import pytest

from mcgyvr.serving import run
from tests import callergates as cg

RELEASE = f"door:{run.LEASE_RELEASE.script}"


def _stubborn(root: Path, log: Path) -> None:
    """A gate that ignores TERM, with a child in its group that ignores it too."""
    cg.executable(
        root / "stubborn.py",
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import os, signal, subprocess, sys, time",
                "signal.signal(signal.SIGTERM, signal.SIG_IGN)",
                "child = subprocess.Popen([sys.executable, '-c', "
                "'import signal, time; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(600)'])",
                "time.sleep(0.5)",
                f"with open({str(log)!r}, 'a') as out:",
                "    out.write(f'caller:stubborn pids={os.getpid()},{child.pid}\\n')",
                "time.sleep(600)",
                "",
            ]
        ),
    )


def _pids(log: Path) -> list[int]:
    for line in cg.log_lines(log):
        match = re.match(r"caller:stubborn pids=(\d+),(\d+)", line)
        if match:
            return [int(match.group(1)), int(match.group(2))]
    raise AssertionError(f"the gate never started: {cg.log_lines(log)}")


def _release_that_looks(work: Path, log: Path) -> None:
    """A lease release that writes which of the gate's processes still run."""
    cg.executable(
        work / "lease-release.py",
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import os, re",
                f"text = open({str(log)!r}).read()",
                "found = re.search(r'caller:stubborn pids=(\\d+),(\\d+)', text)",
                "alive = []",
                "for pid in (found.groups() if found else ()):",
                "    try:",
                "        os.kill(int(pid), 0)",
                "        alive.append(pid)",
                "    except ProcessLookupError:",
                "        pass",
                f"with open({str(log)!r}, 'a') as out:",
                f"    out.write('{RELEASE} alive=' + ','.join(alive) + '\\n')",
                "",
            ]
        ),
    )


@pytest.mark.parametrize(
    ("signals", "gap", "phase"),
    [
        ((), 0.0, "after"),
        ((signal.SIGTERM,), 0.0, "after"),
        ((signal.SIGTERM, signal.SIGINT), 1.0, "after"),
        ((signal.SIGTERM, signal.SIGINT), None, "before"),
        ((signal.SIGTERM, signal.SIGINT), None, "after"),
        ((signal.SIGTERM, signal.SIGINT), None, "always"),
    ],
    ids=[
        "its bound",
        "one signal",
        "a second signal during the grace",
        "TERM and INT back to back, before",
        "TERM and INT back to back, after",
        "TERM and INT back to back, always",
    ],
)
def test_a_stubborn_gate_is_killed_with_its_child_before_the_lease_is_released(
    signals: tuple[signal.Signals, ...], gap: float | None, phase: str, tmp_path: Path
) -> None:
    """Signals ``gap`` seconds apart; with no gap, both are pending at once.

    To have both pending when the door next runs, the door is stopped while
    they are sent and continued after.
    """
    work = tmp_path / "work"
    work.mkdir()
    log = work / "order.log"
    root = work / "caller"
    _stubborn(root, log)
    _release_that_looks(work, log)
    gate = cg.entry("stubborn.py", phase)
    # Reached only when no signal is sent: the gate outlives it otherwise.
    gate["timeout_s"] = 120 if signals else 2
    listed = cg.write_list(work / "gates.json", str(root), [gate])
    compose = cg.compose_file(work / "compose.yaml")
    door = cg.driven_door(work, log, cg.serve_argv(compose, "--gates", str(listed)))
    left: list[int] = []
    try:
        deadline = time.monotonic() + 60
        while not any(line.startswith("caller:stubborn") for line in cg.log_lines(log)):
            assert door.poll() is None, door.communicate()
            assert time.monotonic() < deadline, cg.log_lines(log)
            time.sleep(0.1)
        if gap is None:
            os.kill(door.pid, signal.SIGSTOP)
            for sig in signals:
                os.kill(door.pid, sig)
            os.kill(door.pid, signal.SIGCONT)
        else:
            for index, sig in enumerate(signals):
                if index:
                    time.sleep(gap)
                door.send_signal(sig)
        # The grace is 5 s and the gates live 600 s: a door still running
        # after 60 s did not end them. The door's stderr is not read before
        # it exits, since a gate left running holds it open.
        door.wait(timeout=60)
        left = [pid for pid in _pids(log) if cg.alive(pid)]
    finally:
        cg.stop_door(door, _pids(log) if _started(log) else ())
    _, said = door.communicate(timeout=30)

    released = [line for line in cg.log_lines(log) if line.startswith(RELEASE)]
    # A `before` gate runs before the lease is taken: nothing is released.
    assert released == ([] if phase == "before" else [f"{RELEASE} alive="]), (
        released,
        said,
    )
    assert left == [], (left, said)


def test_the_release_waits_until_the_killed_group_is_gone(tmp_path: Path) -> None:
    """A killed child stays in its group until it is reaped; the release waits.

    Under a parent that reaps an orphan only a while after it died, the gate's
    killed child is still a member of the group when the gate itself is gone.
    The door waits for the group to be empty before it releases the lease.
    """
    work, log, listed, compose = _stubborn_list(tmp_path)
    door = cg.driven_door(
        work, log, cg.serve_argv(compose, "--gates", str(listed)), reap_after=1.5
    )
    try:
        door.wait(timeout=60)
    finally:
        cg.stop_door(door, _pids(log) if _started(log) else ())
    _, said = door.communicate(timeout=30)

    released = [line for line in cg.log_lines(log) if line.startswith(RELEASE)]
    assert released == [f"{RELEASE} alive="], (released, said)


def test_a_signal_after_kill_does_not_hurry_the_release(tmp_path: Path) -> None:
    """A signal that arrives while the door waits for the killed group waits too.

    The gate's killed child stays in the group until its slow parent reaps it.
    A TERM to the door in that wait is ignored like one in the grace: the
    door refuses the gate for its bound, not as an interrupted run, and the
    lease is released only once the group is empty.
    """
    work, log, listed, compose = _stubborn_list(tmp_path)
    door = cg.driven_door(
        work, log, cg.serve_argv(compose, "--gates", str(listed)), reap_after=1.5
    )
    try:
        deadline = time.monotonic() + 60
        while not _started(log):
            assert door.poll() is None, door.communicate()
            assert time.monotonic() < deadline, cg.log_lines(log)
            time.sleep(0.1)
        gate, _ = _pids(log)
        driver = _parent(gate)
        # The door reaps its gate right after KILL; the child it leaves is
        # then a zombie of the slow reaper, still in the group, for 1.5 s.
        while cg.alive(gate):
            assert time.monotonic() < deadline, cg.log_lines(log)
            time.sleep(0.02)
        time.sleep(0.5)
        os.kill(driver, signal.SIGTERM)
        door.wait(timeout=60)
    finally:
        cg.stop_door(door, _pids(log) if _started(log) else ())
    _, said = door.communicate(timeout=30)

    released = [line for line in cg.log_lines(log) if line.startswith(RELEASE)]
    assert released == [f"{RELEASE} alive="], (released, said)
    assert door.returncode == 2, (door.returncode, said)
    assert "ran past its bound of 2 s" in said and "interrupted" not in said, said


def test_a_door_that_adopts_orphans_reaps_its_gates_group(tmp_path: Path) -> None:
    """A door that adopts the processes orphaned below it reaps the gate's group.

    Run as PID 1 or as a child subreaper, the door itself adopts the gate's
    killed child, and nobody else will reap it: the door does, and the lease
    is released with nothing of the gate's group left.
    """
    work, log, listed, compose = _stubborn_list(tmp_path)
    door = cg.driven_door(
        work, log, cg.serve_argv(compose, "--gates", str(listed)), subreaper=True
    )
    try:
        door.wait(timeout=60)
    finally:
        cg.stop_door(door, _pids(log) if _started(log) else ())
    _, said = door.communicate(timeout=30)

    released = [line for line in cg.log_lines(log) if line.startswith(RELEASE)]
    assert released == [f"{RELEASE} alive="], (released, said)


def _stubborn_list(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """The folder, log, list and compose file of one stubborn `after` gate.

    Its bound is 2 s, and the lease release writes which of its processes
    still run.
    """
    work = tmp_path / "work"
    work.mkdir()
    log = work / "order.log"
    root = work / "caller"
    _stubborn(root, log)
    _release_that_looks(work, log)
    gate = cg.entry("stubborn.py", "after")
    gate["timeout_s"] = 2
    listed = cg.write_list(work / "gates.json", str(root), [gate])
    return work, log, listed, cg.compose_file(work / "compose.yaml")


def _started(log: Path) -> bool:
    return any(line.startswith("caller:stubborn") for line in cg.log_lines(log))


def _parent(pid: int) -> int:
    """The parent of a running process, from ``/proc``."""
    stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    return int(stat.rsplit(")", 1)[1].split()[1])
