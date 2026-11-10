"""The one lease answers every operation on every lease state as the bash scripts did.

There is one lease, :mod:`mcgyvr.serving.leasefile`: this machine runs it itself
when it is reached without ssh (`gatelib._local_lease`), and every other rig,
Linux, macOS or Windows, is shipped it as a program (`shipped.lease`). A Linux
rig was sent five bash scripts before; the table here is what those scripts
did. For every operation over every state a lease file can be in (none, this
run's, another run's, blank), each way the lease is reached ends with the
table's status, prints the table's lease, and leaves the table's file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from mcgyvr.serving import gatelib
from tests.remote_rigs import FakeShell, record_rig

MINE = gatelib.new_lease("up", 4242)
OTHER = gatelib.new_lease("down", 4343)
MINE_LINE = MINE.line() + "\n"
OTHER_LINE = OTHER.line() + "\n"
BLANK = "  \n\t\n"
#: The lease file each case starts from; None is no file in the lease folder.
STATES = {"none": None, "mine": MINE_LINE, "other": OTHER_LINE, "blank": BLANK}
OPS = {
    "read": {},
    "take_free": {"line": MINE.line()},
    "take_stale_blank": {"held": "", "line": MINE.line()},
    "take_stale_other": {"held": OTHER.lease_id, "line": MINE.line()},
    "stamp": {"held": MINE.lease_id, "line": MINE.line() + "x"},
    "release": {"held": MINE.lease_id},
}
STAMPED = MINE.line() + "x\n"
#: (op, state) -> (status, what it prints, the lease file after; None is gone),
#: as the bash scripts a Linux rig was sent answered them.
TABLE: dict[tuple[str, str], tuple[int, str, str | None]] = {
    ("read", "none"): (0, "", None),
    ("read", "mine"): (0, MINE_LINE, MINE_LINE),
    ("read", "other"): (0, OTHER_LINE, OTHER_LINE),
    ("read", "blank"): (0, BLANK, BLANK),
    ("take_free", "none"): (0, "", MINE_LINE),
    ("take_free", "mine"): (1, "", MINE_LINE),
    ("take_free", "other"): (1, "", OTHER_LINE),
    ("take_free", "blank"): (1, "", BLANK),
    ("take_stale_blank", "none"): (0, "", MINE_LINE),
    ("take_stale_blank", "mine"): (3, "", MINE_LINE),
    ("take_stale_blank", "other"): (3, "", OTHER_LINE),
    ("take_stale_blank", "blank"): (0, "", MINE_LINE),
    ("take_stale_other", "none"): (3, "", None),
    ("take_stale_other", "mine"): (3, "", MINE_LINE),
    ("take_stale_other", "other"): (0, "", MINE_LINE),
    ("take_stale_other", "blank"): (3, "", BLANK),
    ("stamp", "none"): (3, "", None),
    ("stamp", "mine"): (0, "", STAMPED),
    ("stamp", "other"): (3, "", OTHER_LINE),
    ("stamp", "blank"): (3, "", BLANK),
    ("release", "none"): (0, "", None),
    ("release", "mine"): (0, "", None),
    ("release", "other"): (0, "", OTHER_LINE),
    ("release", "blank"): (0, "", BLANK),
}
#: How the lease is reached: this machine without ssh, or a rig over ssh whose
#: rig file records nothing (a Linux rig, as every rig was) or Windows.
WAYS = ("local", "linux", "windows")


def test_the_table_has_every_operation_on_every_state() -> None:
    assert set(TABLE) == {(op, state) for op in OPS for state in STATES}


def _set(home: Path, state: str | None) -> Path:
    lease = home / ".mcgyvr" / "lease"
    lease.parent.mkdir(parents=True, exist_ok=True)
    if state is not None:
        lease.write_text(state)
    return lease


@pytest.mark.parametrize("way", WAYS)
@pytest.mark.parametrize("state", sorted(STATES))
@pytest.mark.parametrize("op", sorted(OPS))
def test_each_way_the_lease_is_reached_ends_as_the_table_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, op: str, state: str, way: str
) -> None:
    name = "take_stale" if op.startswith("take_stale") else op
    fields = OPS[op]
    home = tmp_path / "rig-home"
    lease = _set(home, STATES[state])
    monkeypatch.setenv("MCGYVR_RIGS", str(tmp_path / "rigs"))
    if way == "local":
        monkeypatch.setenv("HOME", str(home))
        done = gatelib._local_lease(name, **fields)
    else:
        if way == "windows":
            record_rig(monkeypatch, tmp_path, "box1", "windows-one-card")
        assert gatelib.rig_system("box1") == way
        shell = FakeShell(way, home)
        monkeypatch.setattr(gatelib, "ssh", shell)
        done = gatelib._lease_op("box1", name, **cast(Any, fields))
        ((command, _stdin),) = shell.sent
        shape = "powershell " if way == "windows" else "echo "
        assert command.startswith(shape), command[:80]

    status, printed, after = TABLE[(op, state)]
    assert done.returncode == status, (done.stderr, op, state, way)
    assert done.stdout == printed
    assert (lease.read_text() if lease.exists() else None) == after
