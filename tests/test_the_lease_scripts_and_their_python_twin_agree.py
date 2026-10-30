"""The lease's two implementations agree: the rig's shell scripts and the local Python.

A rig reached over ssh takes, stamps and releases its lease with the shell
scripts `gatelib` ships (`bash -s -- lease`); this machine reached without ssh
does the same in Python (`gatelib._local_lease`). For every operation over
every state a lease file can be in (none, this run's, another run's, blank),
both end with the same status, print the same lease, and leave the same file.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from mcgyvr.serving import gatelib

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")

MINE = gatelib.new_lease("up", 4242)
OTHER = gatelib.new_lease("down", 4343)
STATES = {
    "none": None,
    "mine": MINE.line() + "\n",
    "other": OTHER.line() + "\n",
    "blank": "  \n\t\n",
}
OPS = {
    "read": {},
    "take_free": {"line": MINE.line()},
    "take_stale_blank": {"held": "", "line": MINE.line()},
    "take_stale_other": {"held": OTHER.lease_id, "line": MINE.line()},
    "stamp": {"held": MINE.lease_id, "line": MINE.line() + "x"},
    "release": {"held": MINE.lease_id},
}


def _set(home: Path, state: str | None) -> Path:
    lease = home / ".mcgyvr" / "lease"
    lease.parent.mkdir(parents=True, exist_ok=True)
    if state is not None:
        lease.write_text(state)
    return lease


def _after(lease: Path) -> str | None:
    return lease.read_text() if lease.exists() else None


@pytest.mark.parametrize("state", sorted(STATES))
@pytest.mark.parametrize("op", sorted(OPS))
def test_the_script_and_the_python_agree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, op: str, state: str
) -> None:
    name = "take_stale" if op.startswith("take_stale") else op
    fields = OPS[op]

    shell_home = tmp_path / "shell"
    shell_lease = _set(shell_home, STATES[state])
    script = gatelib._LEASE_SCRIPTS[name].format(
        dir=gatelib.LEASE_DIR, file=gatelib.LEASE_FILE, **fields
    )
    by_shell = subprocess.run(
        ["bash", "-s", "--", "lease"],
        input=script,
        capture_output=True,
        text=True,
        env={"HOME": str(shell_home), "PATH": "/usr/bin:/bin"},
        check=False,
    )

    python_home = tmp_path / "python"
    python_lease = _set(python_home, STATES[state])
    monkeypatch.setenv("HOME", str(python_home))
    by_python = gatelib._local_lease(name, **fields)

    assert by_python.returncode == by_shell.returncode, (by_shell.stderr, op, state)
    assert by_python.stdout == by_shell.stdout
    assert _after(python_lease) == _after(shell_lease)
