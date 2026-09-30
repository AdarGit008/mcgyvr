"""A rig's identity is minted by the slot its card sits in."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SNAPSHOT_SH = REPO / "src" / "mcgyvr" / "serving" / "gate-scripts" / "rig-snapshot.sh"


def _snapshot(**overrides: str) -> dict[str, str]:
    """One made-up one-card rig reading, as ``rig-snapshot.sh`` prints it."""
    values = {
        "hostname": "invented-box-1.invalid",
        "cpu_model": "Made_Up_CPU_A",
        "cpu_max_mhz": "4500",
        "ram_mt_s": "3200",
        "pl1_uw": "95000000",
        "pl2_uw": "120000000",
        "gpu_name": "Made_Up_Card_A",
        "gpu_vram_mib": "12288",
        "gpu_cc": "8.6",
        "gpu_slot": "00000000:01:00.0",
        "os_machine_id": hashlib.sha256(b"invented-box-1").hexdigest()[:16],
        "kernel": "6.8.0-100-madeup",
        "driver": "580.178.04",
        "docker": "29.7.2",
    }
    values.update(overrides)
    return values


def _reader_body(*names: str) -> str:
    """The ``set -u``/``fail``/``tok`` prefix plus each named function."""
    text = SNAPSHOT_SH.read_text(encoding="utf-8")
    parts = [text.split("\nuptime_since()", 1)[0]]
    for name in names:
        match = re.search(
            rf"^{name}\(\) \{{\n.*?^\}}\n", text, re.MULTILINE | re.DOTALL
        )
        assert match, f"rig-snapshot.sh defines no {name}() reader"
        parts.append(match.group(0))
    return "\n".join(parts)


def _stub_smi(path: Path, rows: str) -> None:
    """A fake ``nvidia-smi`` on PATH that answers the csv query with ``rows``."""
    stub = path / "nvidia-smi"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'case "$*" in\n'
        "  *query-compute-apps*) exit 0 ;;\n"
        "esac\n"
        "cat <<'EOF'\n" + rows + "EOF\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)


def _run_nvidia(tmp_path: Path, rows: str) -> str:
    _stub_smi(tmp_path, rows)
    done = subprocess.run(
        ["bash", "-c", _reader_body("others_of", "nvidia") + "\nnvidia\n"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


def test_the_same_card_in_another_slot_names_another_rig() -> None:
    from mcgyvr.fleet.ids import rig_id

    here = rig_id(_snapshot())
    moved = rig_id(_snapshot(gpu_slot="00000000:02:00.0"))
    again = rig_id(_snapshot())
    assert moved != here
    assert again == here


def test_gpu_others_is_hashed_only_when_non_empty() -> None:
    from mcgyvr.fleet.ids import rig_id

    absent = rig_id(_snapshot())
    empty = rig_id(_snapshot(gpu_others=""))
    assert empty == absent
    second = rig_id(_snapshot(gpu_others="00000000:04:00.0:Made_Up_Card_B:12288:8.6"))
    assert second != absent


def test_gpu_others_is_hashed_exactly_as_printed() -> None:
    from mcgyvr.fleet.ids import RIG_HARDWARE, RIG_SYSTEM, digest, rig_id

    snapshot = _snapshot(
        gpu_others="00000000:0a:00.0:Made_Up_Card_High:8192:8.6;"
        "00000000:01:00.0:Made_Up_Card_Low:4096:7.0"
    )
    hardware = {key: snapshot[key] for key in RIG_HARDWARE}
    hardware["gpu_others"] = snapshot["gpu_others"]
    expected = digest(
        "rig-",
        {
            "host": snapshot["hostname"],
            "hardware": hardware,
            "system": {key: snapshot[key] for key in RIG_SYSTEM},
        },
    )
    assert rig_id(snapshot) == expected
    assert rig_id(_snapshot(gpu_others="A;B")) != rig_id(_snapshot(gpu_others="B;A"))


def test_a_snapshot_missing_gpu_slot_is_refused_by_name() -> None:
    from mcgyvr.fleet.ids import rig_id

    snapshot = _snapshot()
    del snapshot["gpu_slot"]
    with pytest.raises(ValueError, match="gpu_slot"):
        rig_id(snapshot)


def test_the_nvidia_reader_prints_gpu_slot_and_gpu_others(tmp_path: Path) -> None:
    one = _run_nvidia(
        tmp_path,
        "Made_Up_Card_A,00000000:01:00.0,12288,8.6,580.178.04,0,0,12288\n",
    )
    lines = dict(line.split("=", 1) for line in one.splitlines() if line)
    assert lines["gpu_slot"] == "00000000:01:00.0"
    assert lines["gpu_others"] == ""

    many = _run_nvidia(
        tmp_path,
        "Made_Up_Card_Primary,00000000:04:00.0,6144,7.5,580.178.04,399,0,399\n"
        "Made_Up_Card_High,00000000:0a:00.0,8192,8.6,580.178.04,0,0,8192\n"
        "Made_Up_Card_Low,00000000:01:00.0,4096,7.0,580.178.04,0,0,4096\n",
    )
    lines = dict(line.split("=", 1) for line in many.splitlines() if line)
    assert lines["gpu_slot"] == "00000000:04:00.0"
    assert lines["gpu_others"] == (
        "00000000:01:00.0:Made_Up_Card_Low:4096:7.0;"
        "00000000:0a:00.0:Made_Up_Card_High:8192:8.6"
    )
