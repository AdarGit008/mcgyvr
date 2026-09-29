"""The served machine's lease does not follow the local config folder.

Promise: a user who moves mcgyvr's config folder on the machine they type on
moves the settings kept there, and nothing that a served machine keeps on
itself. The lease that holds a served machine for one run at a time is a file
in that machine's own home folder, named the same by every run that reaches
it, whichever machine the run starts from and wherever that machine keeps its
config folder; two runs that named it differently would each find the machine
free.

Nothing is reached: the transport the lease scripts travel over is replaced by
one that records what would have been sent.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mcgyvr.fleet import roots
from mcgyvr.serving import gatelib

HOST = "served.invalid"
LEASE = gatelib.Lease(
    lease_id="0123456789abcdef",
    profile="live",
    holder="someone@typing.invalid",
    machine="typing",
    pid=4242,
    started_at="2026-01-01T00:00:00Z",
    campaign="serve",
    step="up",
)


def _sent(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every lease script a run sends: read, take a free machine, take over a
    held lease, stamp and release."""
    sent: list[str] = []

    def machine(
        host: str, command: str, stdin: str | None
    ) -> subprocess.CompletedProcess[str]:
        sent.append(f"{host}\n{command}\n{stdin}")
        return subprocess.CompletedProcess([command], 0, stdout="", stderr="")

    monkeypatch.setattr(gatelib, "_over_ssh", machine)
    gatelib.lease_read(HOST)
    gatelib.lease_take(HOST, LEASE, held=None)
    gatelib.lease_take(HOST, LEASE, held=LEASE)
    gatelib.lease_stamp(HOST, LEASE, "run-1")
    gatelib.lease_release(HOST, LEASE.lease_id)
    return sent


def test_moving_the_config_folder_leaves_every_lease_script_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MCGYVR_HOME", raising=False)
    before = _sent(monkeypatch)

    moved = tmp_path / "settings"
    monkeypatch.setenv("MCGYVR_HOME", str(moved))
    assert roots.home() == moved, "the config folder did not move"
    after = _sent(monkeypatch)

    assert after == before
    assert len(after) == 5
    assert all(gatelib.LEASE_FILE in script for script in after), after
    assert not any(str(moved) in script for script in after), after


def test_the_lease_is_named_from_the_served_machines_own_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (gatelib.LEASE_DIR, gatelib.LEASE_FILE):
        assert name.startswith("~/"), name
    local = str(Path.home())
    assert not any(local in script for script in _sent(monkeypatch))
