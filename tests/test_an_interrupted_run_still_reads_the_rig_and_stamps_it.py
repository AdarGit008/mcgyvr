"""Gate 7 runs on the interrupt path too — that is the path it exists for.

A hard lock takes the ssh pipe with it, and the run whose end state is
unknown is exactly the one that ended silently; Ctrl-C on a hung health loop
is the same shape. The archived door's first cut ran gate 7 INSIDE the
``INT``/``TERM`` trap handler, where the nested rig read came back with the
signal's status and no output, so every interrupted run reported "the rig
could not be re-read … its end state is unknown" and the ``### RIGMOVED``
comparison was never reached.

So the signal only ends the entry that was running; gates 7 and 8 run in the
door's main flow, and the door exits 130 afterwards (``run.py:main``). The
signal is delivered to the door's whole process group, as a terminal
delivers Ctrl-C; the rig reads differently once the step has run.
"""

from __future__ import annotations

import os
import signal
import time
from pathlib import Path

import pytest

from tests import onedoor
from tests.onedoor import Scenario


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM], ids=["INT", "TERM"])
def test_a_signal_during_the_step_still_stamps_a_rig_that_moved(
    tmp_path: Path, sig: signal.Signals
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    flag = tmp_path / "step-ran"
    onedoor.add_step(
        root,
        "alpha",
        "1-probe.sh",
        onedoor.probe_step(tmp_path / "e", after=f"touch '{flag}'\nsleep 120"),
    )
    onedoor.rig_stub(onedoor.stubs_dir(root), "srv1", moved_flag=flag)

    proc = onedoor.door_process(root, Scenario("alpha", "1-probe.sh"))
    try:
        deadline = time.monotonic() + 120
        while not flag.exists():
            assert proc.poll() is None, proc.communicate()
            assert time.monotonic() < deadline, "the step never reached its hang"
            time.sleep(0.1)
        os.killpg(proc.pid, sig)
        _, stderr = proc.communicate(timeout=120)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
    assert proc.returncode == 130, (proc.returncode, stderr)
    assert "pl1_uw" in stderr, stderr
    assert "could not be re-read" not in stderr, stderr
    artifact = onedoor.envelope(root, "alpha") / "probe.tsv"
    lines = artifact.read_text(encoding="utf-8").splitlines()
    moved = [line for line in lines if line.startswith("### RIGMOVED")]
    assert moved, f"no ### RIGMOVED after an interrupt under a moved rig:\n{lines}"
    assert lines.index(moved[0]) > lines.index(
        next(line for line in lines if line.startswith("### END"))
    )
