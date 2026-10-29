"""A Mac or Windows rig is leased by the one Python lease, shipped as the reader is.

A Windows rig has an interpreter but no bash, so a rig whose rig file records
macOS or Windows is sent the Python lease (``mcgyvr.serving.leasefile``,
assembled with ``hostos``): the one this machine runs on itself when it is
reached without ssh. Taken, read, stamped and released through gatelib against
a fake rig shell that runs what it is sent, the lease lands in the rig's own
``~/.mcgyvr/lease`` and nowhere else, and a second take finds it held.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.serving import gatelib
from tests.remote_rigs import FakeShell, record_rig


@pytest.mark.parametrize("label", ["unified-laptop", "windows-one-card"])
def test_the_lease_is_taken_stamped_and_released_on_the_rig(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, label: str
) -> None:
    record_rig(monkeypatch, tmp_path, "box1", label)
    system = gatelib.recorded_os("box1")
    assert system in ("darwin", "windows")
    shell = FakeShell(str(system), tmp_path / "rig-home")
    monkeypatch.setattr(gatelib, "ssh", shell)
    mine = gatelib.new_lease("up", 4242)
    other = gatelib.new_lease("down", 4343)

    assert gatelib.lease_read("box1") is None
    assert gatelib.lease_take("box1", mine, held=None) is None
    held = gatelib.lease_read("box1")
    assert held is not None and held.lease_id == mine.lease_id
    taken = gatelib.lease_take("box1", other, held=None)
    assert taken is not None and taken.lease_id == mine.lease_id
    stamped = gatelib.lease_stamp("box1", mine, "run-1")
    assert stamped.run_id == "run-1"
    on_rig = tmp_path / "rig-home" / ".mcgyvr" / "lease"
    assert on_rig.read_text() == stamped.line() + "\n"
    assert gatelib.lease_release("box1", mine.lease_id)
    assert not on_rig.exists()
    # Every call was the shipped Python lease, never bash.
    assert shell.sent
    assert all("bash" not in command for command, _ in shell.sent)
    if system == "windows":
        assert all(command.startswith("powershell ") for command, _ in shell.sent)
    else:
        assert all(" | base64 -d | python3 -I -B - " in c for c, _ in shell.sent)
