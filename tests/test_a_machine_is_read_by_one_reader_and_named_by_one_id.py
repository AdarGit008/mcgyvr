"""A machine is read by one reader, and named by one id.

There is only one script that reads a user's hardware. The
one reader is :mod:`mcgyvr.serving.rigscan`: the door ships it to a rig as
``python3 -I -B -``, and the product imports it here. Its one document carries
the short reading (the machine id and every card, on any vendor), the capacity
scan :meth:`mcgyvr.scan.Scan.from_json` reads, and the snapshot the door's
gates hold a run to. Every snapshot key has a value or is named unread with
why: never a placeholder.

One id names the machine: ``rig-`` over its machine id and its cards' names
and sizes (:func:`mcgyvr.fleet.ids.rig_id`). The lock pins it, live admission
compares it, and the hub hears it as the hello's ``machine_id``. The kernel,
the driver and docker are not in it: a driver upgrade is a machine that
changed, not a new machine.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tests._paths import REPO
from tests.machine_shapes import shape
from tests.machinereader import machine_reading, run, stage

SERVING = REPO / "src" / "mcgyvr" / "serving"
GATE_SCRIPTS = SERVING / "gate-scripts"

#: The document's parts, as the door and the product read them.
DOCUMENT_KEYS = {
    "machine",
    "cards",
    "card_sources",
    "unsized",
    "unread",
    "memory",
    "gpus",
    "cpu",
    "bandwidth",
    "disk",
    "models_on_disk",
    "docker",
    "network",
    "home",
    "snapshot",
    "notes",
    "facts",
}


def _whole(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """The reader's whole document of an invented one-card machine, read here."""
    from mcgyvr.serving import rigscan

    answers = {
        "--query-gpu=index,memory.total,memory.used,memory.free,name": (
            "0, 12288, 17, 11890, Example Card A\n"
        ),
        "--query-gpu=index,pci.bus_id,compute_cap,driver_version,memory.reserved": (
            "0, 00000000:01:00.0, 8.6, 580.1, 381\n"
        ),
    }

    def run_tool(argv: Any, *, bound: float = 0.0) -> tuple[str | None, str | None]:
        if argv[0] == "nvidia-smi":
            return answers.get(argv[1]), None
        if argv[:2] == ("docker", "version"):
            return "29.7.2\n", None
        return None, None

    monkeypatch.setattr(rigscan, "_run", run_tool)
    monkeypatch.setattr(rigscan, "measure_bandwidth", lambda root="": None)
    root = tmp_path / "root"
    (root / "etc").mkdir(parents=True)
    (root / "etc" / "machine-id").write_text("ab" * 16 + "\n", encoding="utf-8")
    (root / "proc" / "sys" / "kernel").mkdir(parents=True)
    (root / "proc" / "sys" / "kernel" / "hostname").write_text("box-1\n")
    (root / "proc" / "meminfo").write_text(
        "MemTotal: 16000000 kB\nMemAvailable: 9000000 kB\nSwapTotal: 0 kB\n"
    )
    return rigscan.scan(weights_dir=str(tmp_path / "weights"), root=str(root))


def test_no_other_reader_of_a_machine_is_shipped() -> None:
    assert not (GATE_SCRIPTS / "rig-snapshot.sh").exists()
    assert not (GATE_SCRIPTS / "machine-read.sh").exists()
    assert not (REPO / "src" / "mcgyvr" / "fleet" / "machine.py").exists()
    from mcgyvr.serving.run import READERS

    assert SERVING / "rigscan.py" in READERS


def test_the_one_document_carries_the_scan_and_the_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from mcgyvr.scan import Scan
    from mcgyvr.serving import rigscan

    document = _whole(monkeypatch, tmp_path)
    assert set(document) == DOCUMENT_KEYS
    scan = Scan.from_json(json.dumps(document))
    assert [(g.name, g.vram.total_mib, g.vram.free_mib) for g in scan.gpus] == [
        ("Example Card A", 12288, 11890)
    ]
    assert scan.docker == "29.7.2"
    snapshot = document["snapshot"]
    assert snapshot["gpu_name"] == "Example_Card_A"
    assert snapshot["gpu_slot"] == "00000000:01:00.0"
    assert snapshot["driver"] == "580.1"
    assert snapshot["gpu_reserve_mib"] == "381"
    assert snapshot["os_machine_id"] == document["machine"]["id"]
    unread = {u["field"] for u in document["unread"]}
    for key in rigscan.SNAPSHOT_KEYS:
        valued = key in snapshot
        named = f"snapshot.{key}" in unread
        assert valued != named, key
        assert not valued or not re.search(r"\s", snapshot[key]), key
        assert snapshot.get(key) not in ("NA", "unread"), key


def test_the_rig_id_is_the_machine_id_and_the_cards_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from mcgyvr.fleet import ids

    document = _whole(monkeypatch, tmp_path)
    named = ids.rig_id(document)
    assert named == ids.digest(
        "rig-",
        {
            "machine_id": document["machine"]["id"],
            "cards": [{"name": "Example Card A", "total_mib": 12288}],
        },
    )
    upgraded = {
        **document,
        "snapshot": {**document["snapshot"], "driver": "590.2", "kernel": "7.0.0"},
        "docker": "30.0.0",
    }
    assert ids.rig_id(upgraded) == named


def test_the_retired_machine_prefix_names_nothing() -> None:
    from mcgyvr.fleet import ids

    assert "mch-" not in ids.IDENTITY_PREFIXES
    with pytest.raises(ValueError, match="retired"):
        ids.digest("mch-", {})


def test_a_reading_shipped_as_the_door_ships_it_is_named_by_the_same_id(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import ids
    from mcgyvr.rig import hardware, protocol

    document = machine_reading(shape("several-sizes"), tmp_path)
    report = hardware.read(reader=lambda: document)
    assert report.machine_id == ids.rig_id(document)
    assert report.machine_id.startswith("rig-")
    assert protocol.MACHINE_ID.fullmatch(report.machine_id)


def test_the_read_only_line_admits_exactly_the_shipped_reader(tmp_path: Path) -> None:
    from mcgyvr.serving import gatelib

    line = gatelib.scan_read_command()
    assert gatelib._read_only_command(line)
    blob = line.removeprefix("echo ").split(" ", 1)[0]
    tampered = "A" + blob[1:] if blob[0] != "A" else "B" + blob[1:]
    assert not gatelib._read_only_command(line.replace(blob, tampered))
    assert not gatelib._read_only_command(line + " --cards")
    assert not gatelib._read_only_command(f"echo {blob} | base64 -d | bash -s")
    assert not gatelib._read_only_command(gatelib.cards_read_command())
    assert not hasattr(gatelib, "rig_snapshot_read_command")


def test_the_short_reading_shipped_as_python_names_no_card_it_cannot_size(
    tmp_path: Path,
) -> None:
    ran = run(stage(shape("one-card")), tmp_path)
    assert ran.returncode == 0, ran.stderr
    document = json.loads(ran.stdout)
    assert set(document) == {
        "machine",
        "cards",
        "card_sources",
        "unsized",
        "unread",
        "memory",
    }
    assert document["card_sources"] == ["nvidia-smi"]


def test_the_lock_refuses_a_rig_id_its_dev_runs_read_does_not_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A dev run files the rig id its read named; the lock holds the pin to it."""
    import copy

    from mcgyvr.fleet import ids, lock
    from tests.fleetlocks import EVIDENCE, FLEET, POLICY, TOLERANCES

    named = ids.rig_id(_whole(monkeypatch, tmp_path))
    evidence = copy.deepcopy(EVIDENCE)
    evidence["rigs"]["box2"]["rig_id"] = named

    def fleet_pinning(pinned: str) -> dict[str, Any]:
        fleet = copy.deepcopy(FLEET)
        fleet["rigs"]["box2"]["rig_id"] = pinned
        return fleet

    stale = "rig-" + "2" * 64
    with pytest.raises(lock.LockRefusedError) as refused:
        lock.write(
            tmp_path / "stale",
            fleet_pinning(stale),
            evidence,
            policy=POLICY,
            tolerances=TOLERANCES,
        )
    said = str(refused.value)
    assert "box2" in said and stale in said and named in said, said
    lock.write(
        tmp_path / "named",
        fleet_pinning(named),
        evidence,
        policy=POLICY,
        tolerances=TOLERANCES,
    )
    assert (tmp_path / "named" / "lock" / "rigs" / named).is_dir()


def test_no_other_code_hashes_a_rig_id() -> None:
    """One spelling: ``ids.rig_id`` is the only ``digest("rig-", ...)`` shipped."""
    spelled = sorted(
        path.relative_to(REPO).as_posix()
        for path in (REPO / "src").rglob("*.py")
        if re.search(r"""digest\(\s*["']rig-["']""", path.read_text("utf-8"))
    )
    assert spelled == ["src/mcgyvr/fleet/ids.py"], spelled
