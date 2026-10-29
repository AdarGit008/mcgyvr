"""The lease's two implementations agree: the rig's shell scripts and the Python.

A Linux rig reached over ssh takes, stamps and releases its lease with the
shell scripts `gatelib` ships (`bash -s -- lease`); this machine reached without
ssh does the same in Python (`gatelib._local_lease`, `mcgyvr.serving.leasefile`),
and a macOS or Windows rig is shipped that same Python as a program
(`shipped.lease`). For every operation over every state a lease file can be in
(none, this run's, another run's, blank), all end with the same status, print
the same lease, and leave the same file.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mcgyvr.serving import gatelib, shipped

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


@pytest.mark.parametrize("state", sorted(STATES))
@pytest.mark.parametrize("op", sorted(OPS))
def test_the_shipped_program_and_the_local_python_agree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, op: str, state: str
) -> None:
    name = "take_stale" if op.startswith("take_stale") else op
    fields = OPS[op]

    sent_home = tmp_path / "shipped"
    sent_lease = _set(sent_home, STATES[state])
    by_program = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-",
            name,
            gatelib.LEASE_DIR,
            *(f"{k}={v}" for k, v in sorted(fields.items())),
        ],
        input=shipped.packed(shipped.lease()),
        capture_output=True,
        env={"HOME": str(sent_home)},
        check=False,
    )

    python_home = tmp_path / "python"
    python_lease = _set(python_home, STATES[state])
    monkeypatch.setenv("HOME", str(python_home))
    by_python = gatelib._local_lease(name, **fields)

    assert by_program.returncode == by_python.returncode, (by_program.stderr, op)
    assert by_program.stdout.decode() == by_python.stdout
    assert _after(sent_lease) == _after(python_lease)
