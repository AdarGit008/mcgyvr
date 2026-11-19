"""The scan's default output is the same with or without the wider reading.

The whole scan now also lists every card with its PCI ids and source
(``devices``) and the CPU's flags and clock (``cpu_detail``). ``mcgyvr scan``
and ``mcgyvr scan --json`` print the same bytes whether the reading carries
them or not, and the json holds the keys it held before; only ``--hardware``
prints them. The short reading (the rig's hello) carries neither.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from tests.machine_shapes import (
    host_reading,
    host_scan_document,
    host_shape,
    host_shapes,
)

NEW_KEYS = ("devices", "cpu_detail")

#: The keys ``mcgyvr scan --json`` prints by default, as it printed them before
#: the wider reading.
DEFAULT_JSON_KEYS = [
    "machine",
    "gpus",
    "memory",
    "cpu",
    "bandwidth",
    "disk",
    "models_on_disk",
    "docker",
    "network",
    "home",
    "host",
    "notes",
    "facts",
]


def _older(document: dict[str, Any]) -> dict[str, Any]:
    """The same reading as an older reader prints it: without the new keys."""
    return {key: value for key, value in document.items() if key not in NEW_KEYS}


def _printed(
    document: dict[str, Any],
    arguments: list[str],
    where: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> str:
    from mcgyvr.cli import main
    from mcgyvr.serving import rigscan

    # Each run starts from no saved rig, in the one folder its report names.
    shutil.rmtree(where, ignore_errors=True)
    monkeypatch.setenv("MCGYVR_RIGS", str(where))
    monkeypatch.setattr(rigscan, "scan", lambda *a, **k: copy.deepcopy(document))
    main(["scan", *arguments])
    return capsys.readouterr().out


def _with_cpu(label: str) -> Any:
    return dataclasses.replace(
        host_shape(label), cpu_flags=("avx", "avx2", "fma"), cpu_max_mhz=3900
    )


@pytest.mark.parametrize(
    "machine", [*host_shapes(), _with_cpu("linux-one-card")], ids=lambda m: m.label
)
@pytest.mark.parametrize("arguments", [[], ["--json"]], ids=["report", "json"])
def test_scan_prints_the_same_bytes_whether_the_reading_is_wider_or_not(
    machine: Any,
    arguments: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = host_scan_document(machine)
    assert set(NEW_KEYS) <= set(document)
    wider = _printed(document, arguments, tmp_path, monkeypatch, capsys)
    older = _printed(_older(document), arguments, tmp_path, monkeypatch, capsys)
    assert wider == older
    assert "Device " not in wider and "CPU ISA" not in wider


@pytest.mark.parametrize("machine", host_shapes(), ids=lambda m: m.label)
def test_scan_json_holds_the_keys_it_held_before(
    machine: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = host_scan_document(machine)
    out = _printed(document, ["--json"], tmp_path, monkeypatch, capsys)
    assert list(json.loads(out)) == DEFAULT_JSON_KEYS


def test_scan_with_hardware_prints_every_card_and_the_cpu_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    machine = _with_cpu("linux-one-card")
    document = host_scan_document(machine)
    out = _printed(document, ["--hardware"], tmp_path / "r", monkeypatch, capsys)
    assert "  Device   nvidia:0  nvidia 0, Example Card A, " in out
    assert "PCI 0x10de:0x" in out and "(nvidia-smi)" in out
    assert "  CPU ISA  has avx avx2 fma; lacks " in out
    assert "(/proc/cpuinfo flags)" in out
    assert "  CPU MHz  3900 max (cpufreq cpuinfo_max_freq)" in out
    text = _printed(
        document, ["--json", "--hardware"], tmp_path / "j", monkeypatch, capsys
    )
    printed = json.loads(text)
    assert list(printed) == [*DEFAULT_JSON_KEYS, *NEW_KEYS]
    assert printed["devices"][0]["read_from"] == "nvidia-smi"
    assert printed["cpu_detail"]["flags"]["avx2"] is True
    assert printed["cpu_detail"]["max_mhz"] == 3900


@pytest.mark.parametrize("machine", host_shapes(), ids=lambda m: m.label)
def test_the_short_reading_carries_none_of_the_wider_reading(machine: Any) -> None:
    """The short reading is the rig's hello and the card read: not widened."""
    short = host_reading(machine)
    assert not set(NEW_KEYS) & set(short)
    whole = host_scan_document(machine)
    assert whole["cards"] == short["cards"]
    assert whole["resources"] == short["resources"]
    assert all(set(card) <= _CARD_KEYS for card in short["cards"])


#: The fields a card of the short reading holds, as before the wider reading.
_CARD_KEYS = {
    "vendor",
    "index",
    "total_mib",
    "used_mib",
    "free_mib",
    "name",
    "kind",
    "backend",
    "figure",
    "how",
    "gpu_cores",
}
