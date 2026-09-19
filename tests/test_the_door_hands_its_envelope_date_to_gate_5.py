"""A run without ``--date`` is filed under the date the door checked it against.

The door names the envelope before any gate runs — a step's own output flag
may name a path inside ``records/evidence/<date>-<campaign>/`` and nowhere
else (``run.py:_check_step_args``) — and gate 5 makes that envelope and mints
the RUN_ID from its date. With no ``--date`` each read the clock for itself,
and only ``--date`` was handed over as ``RUN_DATE``: a run started at
23:59:59 UTC was checked against day D's envelope and filed under D+1's.

The door reads the clock once and gate 5 files under what it read. Here the
door's clock is held at the last second of the fixture's day, and every gate,
a separate process, reads the real one.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests import onedoor

#: The door's process, with its clock held at 23:59:59 UTC on RUN_DATE. The
#: door's path stays in argv, so the gates still find the door among their
#: ancestors.
FROZEN_DOOR = """\
import datetime as real
import runpy
import sys
import types

DAY = tuple(map(int, sys.argv[1].split("-")))


class Clock(real.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(*DAY, 23, 59, 59, tzinfo=tz)


shim = types.ModuleType("datetime")
shim.__dict__.update(real.__dict__)
shim.datetime = Clock
sys.modules["datetime"] = shim
door = sys.argv[2]
sys.argv = sys.argv[2:]
runpy.run_path(door, run_name="__main__")
"""


def test_a_run_without_a_date_is_filed_under_the_envelope_the_door_checked(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    env_file = tmp_path / "e"
    onedoor.add_step(root, "alpha", "1-probe.sh", onedoor.probe_step(env_file))
    wrapper = tmp_path / "frozen_door.py"
    wrapper.write_text(FROZEN_DOOR, encoding="utf-8")
    checked = onedoor.envelope(root, "alpha", onedoor.RUN_DATE)
    step = root / "tools" / "runs" / "campaigns" / "alpha" / "1-probe.sh"
    argv = [
        sys.executable,
        str(wrapper),
        onedoor.RUN_DATE,
        str(root / onedoor.DOOR_REL),
        "--host",
        "srv1",
        "--campaign",
        "alpha",
        "--model",
        onedoor.MODEL,
        "--ctx-per-slot",
        "2048",
        "--step",
        str(step),
        # Admitted by the door only because it is inside day D's envelope.
        "--",
        "--out",
        str(checked / "probe.tsv"),
    ]

    result = subprocess.run(
        argv,
        cwd=root,
        env=onedoor.door_env(root),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )

    assert "REFUSED" not in result.stderr, result.stderr[-1500:]
    assert env_file.exists(), (result.returncode, result.stderr[-1500:])
    handed = onedoor.read_env_file(env_file)
    assert Path(handed["RUN_OUT_DIR"]) == checked, (
        f"the door checked the step against {checked} and gate 5 filed the run "
        f"under {handed['RUN_OUT_DIR']}.\nstderr: {result.stderr[-1500:]}"
    )
    assert handed["RUN_ID"].startswith(f"{onedoor.RUN_DATE}-alpha-probe"), handed
