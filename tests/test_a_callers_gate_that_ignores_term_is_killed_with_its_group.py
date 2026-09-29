"""A caller's gate that ignores TERM is killed with its process group.

The door ends a caller's gate by sending its process group TERM, and KILL
when the group is still there after a grace. A gate and a child of it that
both ignore TERM are killed all the same: at the gate's bound, on one signal
to the door, and on a second signal that arrives while the door waits out
the grace. Both are gone before the lease is released.
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
    "signals",
    [(), (signal.SIGTERM,), (signal.SIGTERM, signal.SIGINT)],
    ids=["its bound", "one signal", "a second signal during the grace"],
)
def test_a_stubborn_gate_is_killed_with_its_child_before_the_lease_is_released(
    signals: tuple[signal.Signals, ...], tmp_path: Path
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    log = work / "order.log"
    root = work / "caller"
    _stubborn(root, log)
    _release_that_looks(work, log)
    gate = cg.entry("stubborn.py", "after")
    # Reached only when no signal is sent: the gate outlives it otherwise.
    gate["timeout_s"] = 120 if signals else 2
    listed = cg.write_list(work / "gates.json", str(root), [gate])
    compose = cg.compose_file(work / "compose.yaml")
    door = cg.driven_door(work, log, cg.serve_argv(compose, "--gates", str(listed)))
    try:
        deadline = time.monotonic() + 60
        while not any(line.startswith("caller:stubborn") for line in cg.log_lines(log)):
            assert door.poll() is None, door.communicate()
            assert time.monotonic() < deadline, cg.log_lines(log)
            time.sleep(0.1)
        for index, sig in enumerate(signals):
            if index:
                time.sleep(1)
            door.send_signal(sig)
        # The grace is 5 s and the gates live 600 s: a door still waiting
        # after 60 s did not kill them.
        _, said = door.communicate(timeout=60)
    finally:
        if door.poll() is None:
            door.kill()
            door.wait()
        try:
            left = [pid for pid in _pids(log) if cg.alive(pid)]
        except AssertionError:
            left = []  # the gate never started; the loop above said so
        for pid in left:  # leave nothing running when the door failed to
            os.kill(pid, signal.SIGKILL)

    assert f"{RELEASE} alive=" in cg.log_lines(log), (cg.log_lines(log), said)
    assert left == [], left


def test_the_release_waits_until_the_killed_group_is_gone(tmp_path: Path) -> None:
    """A killed child stays in its group until it is reaped; the release waits.

    Under a parent that reaps an orphan only a while after it died, the gate's
    killed child is still a member of the group when the gate itself is gone.
    The door waits for the group to be empty before it releases the lease.
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
    compose = cg.compose_file(work / "compose.yaml")
    door = cg.driven_door(
        work, log, cg.serve_argv(compose, "--gates", str(listed)), reap_after=1.5
    )
    try:
        _, said = door.communicate(timeout=60)
    finally:
        if door.poll() is None:
            door.kill()
            door.wait()

    assert f"{RELEASE} alive=" in cg.log_lines(log), (cg.log_lines(log), said)
