"""``mcgyvr scan --rig RIG`` saves the rig's scan as the door's rig file.

Owner, 2026-10-07 (Round 5): the door's user mode holds each run to the rig as
the user described it: ``<rig-file folder>/<rig>.json``, the read-only ssh
scan of the rig (hostname, cards and their memory, RAM, disk, docker version),
over the user's own ssh config and keys. ``mcgyvr setup`` will write it on a
first run; ``mcgyvr scan --rig`` writes it now, and says what moved since the
last one.

Every machine here is invented and stands behind a stub ssh.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from mcgyvr import cli
from mcgyvr.scan import Scan
from mcgyvr.serving import rigfile, rigscan
from tests import onedoor, usermode


def _on_path(stubs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    parts = [str(stubs), str(Path(sys.executable).parent), os.environ["PATH"]]
    monkeypatch.setenv("PATH", os.pathsep.join(parts))


def test_scan_rig_writes_the_rig_file_under_the_config_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "settings"))
    _on_path(usermode.machine(tmp_path), monkeypatch)

    assert cli.main(["scan", "--rig", usermode.RIG]) == 0

    path = tmp_path / "settings" / "rigs" / f"{usermode.RIG}.json"
    assert str(path) in capsys.readouterr().out
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["rig"] == usermode.RIG
    assert saved["hostname"] == usermode.HOSTNAME
    assert saved["cards"] == [
        {"index": 0, "name": "Invented Card 16G", "total_mib": 16384}
    ]
    assert saved["ram_total_gb"] == 62.7
    assert saved["disk"]["free_gb"] == 400.0
    assert saved["docker"] == usermode.DOCKER
    assert rigfile.read(usermode.RIG) == rigfile.from_json(path.read_text("utf-8"))


def test_scan_rig_writes_to_the_named_rigs_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rigs = tmp_path / "rigs-elsewhere"
    monkeypatch.setenv("MCGYVR_RIGS", str(rigs))
    _on_path(usermode.machine(tmp_path), monkeypatch)

    assert cli.main(["scan", "--rig", usermode.RIG]) == 0

    path = rigs / f"{usermode.RIG}.json"
    assert str(path) in capsys.readouterr().out
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["rig"] == usermode.RIG
    assert not (usermode.home() / ".mcgyvr" / "rigs").exists()


def test_a_relative_rigs_folder_is_refused_before_anything_reaches_a_rig(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stubs = usermode.machine(tmp_path)
    _on_path(stubs, monkeypatch)
    monkeypatch.setenv("MCGYVR_RIGS", "relative/rigs")

    assert cli.main(["scan", "--rig", usermode.RIG]) != 0

    said = capsys.readouterr().err
    assert "MCGYVR_RIGS" in said, said
    assert onedoor.ssh_log(stubs) == [], "the rig was reached before the refusal"


def test_a_second_scan_says_what_moved_since_the_last(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stubs = usermode.machine(tmp_path, scan=usermode.scan_payload(ram_gb=31.3))
    _on_path(stubs, monkeypatch)
    assert cli.main(["scan", "--rig", usermode.RIG]) == 0
    capsys.readouterr()
    usermode.set_scan(stubs, usermode.scan_payload(ram_gb=62.7))

    assert cli.main(["scan", "--rig", usermode.RIG]) == 0

    out = capsys.readouterr().out
    assert "moved" in out
    assert "31.3" in out and "62.7" in out
    assert rigfile.read(usermode.RIG) is not None
    assert rigfile.read(usermode.RIG).ram_total_gb == 62.7  # type: ignore[union-attr]


def test_an_unreachable_rig_writes_no_rig_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stubs = usermode.machine(tmp_path)
    (stubs / "ssh-down").touch()
    _on_path(stubs, monkeypatch)

    assert cli.main(["scan", "--rig", usermode.RIG]) != 0
    assert rigfile.read(usermode.RIG) is None
    assert onedoor.ssh_log(stubs), "the rig was never asked"


@pytest.mark.parametrize("name", ["../elsewhere", ".hidden", "a/b", ""])
def test_a_rig_name_that_is_not_a_plain_file_name_is_refused(name: str) -> None:
    with pytest.raises(rigfile.RigFileError):
        rigfile.path(name)


def test_the_rig_scanner_reads_the_docker_version_on_the_rig(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def answered(binary: str, *args: str, timeout: float = 30.0) -> str | None:
        if binary == "docker" and args[:1] == ("version",):
            return f"{usermode.DOCKER}\n"
        return None

    monkeypatch.setattr(rigscan, "_run", answered)
    payload = rigscan.scan()

    assert payload["docker"] == usermode.DOCKER
    assert Scan.from_json(json.dumps(payload)).docker == usermode.DOCKER


def test_a_rig_with_no_docker_reads_as_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rigscan, "_run", lambda *a, **k: None)

    assert rigscan.scan()["docker"] is None
