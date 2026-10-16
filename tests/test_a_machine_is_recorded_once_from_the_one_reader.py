"""A machine is recorded once, and every fact of it comes from the one reader.

``mcgyvr scan``, ``mcgyvr detect``, a serve step's card figures and ``mcgyvr
setup`` take what they know of a machine from :mod:`mcgyvr.serving.rigscan`:
none of them runs a hardware tool of its own. What is read is kept in one
place, the machine's rig file (``$MCGYVR_RIGS/<rig>.json``,
:mod:`mcgyvr.serving.rigfile`), which holds the reading whole: ``mcgyvr scan``
writes this machine's as ``localhost`` and says what moved since the last
one, ``emit`` sizes from it, and the door holds a run to it.

Interactive ``mcgyvr setup`` reads each rig once — this machine without ssh,
a remote one over the read-only ssh line — writes its rig file, and names
the rig from that same reading when the fleet is approved, so a remote rig's
``serve up`` has the rig file its gate 2 asks for.
"""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

#: The one reader's document of an invented one-card machine.
READING: dict[str, Any] = {
    "machine": {"id": "ab" * 8, "id_from": "/etc/machine-id", "host": "box-1"},
    "cards": [
        {
            "vendor": "nvidia",
            "index": 0,
            "name": "Example Card A",
            "total_mib": 12288,
            "used_mib": 17,
            "free_mib": 11890,
        }
    ],
    "card_sources": ["nvidia-smi"],
    "unsized": [],
    "unread": [],
    "memory": {"total_gb": 15.7, "available_gb": 9.0},
    "gpus": [
        {
            "index": 0,
            "name": "Example Card A",
            "vram": {
                "total_mib": 12288,
                "used_mib": 17,
                "free_mib": 11890,
                "reserved_mib": 381,
            },
        }
    ],
    "cpu": {"cores": 6, "threads": 12},
    "bandwidth": {"measured_gbps": 20.0, "how": "an invented copy"},
    "disk": {"path": "/home/user/.cache/mcgyvr/weights", "free_gb": 400.0},
    "models_on_disk": [],
    "docker": "29.7.2",
    "network": {"reached_at": None, "ipv4": []},
    "snapshot": {"driver": "580.1", "kernel": "6.8.0", "gpu_slot": "0:01:00.0"},
    "notes": [],
    "facts": [],
}


@pytest.fixture
def rigs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "rigs"
    monkeypatch.setenv("MCGYVR_RIGS", str(folder))
    return folder


def test_scan_measures_nothing_itself() -> None:
    from mcgyvr import detect, scan
    from mcgyvr.serving import servelib

    for name in (
        "_run",
        "_read_meminfo",
        "_scan_machine",
        "_scan_gpus",
        "_scan_memory",
        "_scan_cpu",
        "_scan_bandwidth",
        "_scan_disk",
        "_scan_models_on_disk",
        "measure_bandwidth",
        "write_scan",
        "load_prior",
        "compare",
        "default_root",
    ):
        assert not hasattr(scan, name), name
    for module in (scan, detect, servelib):
        source = Path(str(module.__file__)).read_text(encoding="utf-8")
        # No tool is named as a command, and no kernel file as a path to open.
        assert '"nvidia-smi"' not in source and '"/proc/meminfo"' not in source


def test_a_scan_of_this_machine_is_the_one_readers_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr import scan
    from mcgyvr.serving import rigscan

    asked: list[tuple[Any, ...]] = []

    def read(*args: Any, **kwargs: Any) -> dict[str, Any]:
        asked.append(args)
        return copy.deepcopy(READING)

    monkeypatch.setattr(rigscan, "scan", read)
    measured = scan.scan()
    assert measured == scan.Scan.from_json(json.dumps(READING))
    assert len(asked) == 1


def test_detect_takes_its_cards_and_ram_from_the_one_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr import detect
    from mcgyvr.serving import rigscan

    monkeypatch.setattr(rigscan, "read_machine", lambda **_: copy.deepcopy(READING))
    gpus, _ = detect.detect_gpus()
    assert [(gpu.name, gpu.vram_gb) for gpu in gpus] == [("Example Card A", 12.0)]
    assert detect.detect_ram_gb()[0] == 15.7


def test_a_serve_steps_card_figures_are_the_readers_short_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.serving import gatelib, servelib

    sent: list[str] = []

    def ssh(host: str, command: str, timeout: float | None = 120.0) -> Any:
        sent.append(command)
        return subprocess.CompletedProcess([], 0, json.dumps(READING), "")

    monkeypatch.setattr(servelib, "ssh", ssh)
    assert servelib.card("box-1") == {"used_mib": 17, "free_mib": 11890}
    assert sent == [gatelib.cards_read_command()]


def test_scan_records_this_machine_once_as_its_rig_file_and_says_what_moved(
    rigs: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.cli import main
    from mcgyvr.exits import Exit
    from mcgyvr.serving import rigscan

    reading = copy.deepcopy(READING)
    monkeypatch.setattr(rigscan, "scan", lambda *a, **k: copy.deepcopy(reading))
    assert main(["scan"]) == Exit.OK
    assert sorted(p.name for p in rigs.iterdir()) == ["localhost.json"]
    saved = json.loads((rigs / "localhost.json").read_text(encoding="utf-8"))
    assert saved["reading"]["snapshot"]["driver"] == "580.1"
    capsys.readouterr()

    reading["snapshot"]["driver"] = "590.2"
    assert main(["scan"]) == Exit.OK
    out = capsys.readouterr().out
    assert "driver 580.1 -> 590.2" in out

    reading["gpus"][0]["vram"]["total_mib"] = 8192
    assert main(["scan"]) == Exit.MISMATCH


def test_setup_reads_a_remote_rig_once_and_writes_its_rig_file(
    rigs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.cli.commands.setup import _rig_id, _setup_scan_rigs
    from mcgyvr.fleet import ids
    from mcgyvr.serving import gatelib, rigfile

    sent: list[str] = []

    def ssh_read_only(host: str, command: str, timeout: float | None = 120.0) -> Any:
        sent.append(command)
        return subprocess.CompletedProcess([], 0, json.dumps(READING), "")

    monkeypatch.setattr(gatelib, "ssh_read_only", ssh_read_only)
    scans, readings = _setup_scan_rigs(("box.invalid",))
    assert sent == [gatelib.scan_read_command()]
    saved = rigfile.read("box.invalid")
    assert saved is not None and saved.hostname == "box-1"
    assert scans["box.invalid"].gpus[0].vram.total_mib == 12288
    assert _rig_id("box.invalid", readings["box.invalid"]) == ids.rig_id(READING)
    assert len(sent) == 1


def test_setup_reads_this_machine_once(
    rigs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.cli.commands.setup import _rig_id, _setup_scan_rigs
    from mcgyvr.serving import rigfile, rigscan

    asked: list[int] = []

    def read(*args: Any, **kwargs: Any) -> dict[str, Any]:
        asked.append(1)
        return copy.deepcopy(READING)

    monkeypatch.setattr(rigscan, "scan", read)
    _, readings = _setup_scan_rigs(("localhost",))
    _rig_id("localhost", readings["localhost"])
    assert asked == [1]
    assert rigfile.read("localhost") is not None
