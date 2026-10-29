"""The machine commands print the host and a unified GPU.

``mcgyvr detect`` says what system the machine runs and lists a unified-memory
GPU as one, and ``mcgyvr scan`` prints the system, each card's backend, a
unified GPU's size as an estimate, the CPU's model, and memory read as a total
alone without promising anything free.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from tests.machine_shapes import host_detection, host_scan_document, host_shape


@pytest.fixture
def rigs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "rigs"
    monkeypatch.setenv("MCGYVR_RIGS", str(folder))
    return folder


def test_detect_prints_the_system_and_the_unified_gpu(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.cli import main
    from mcgyvr.cli.commands import machine as command

    laptop = host_shape("unified-laptop")
    found = host_detection(laptop)
    monkeypatch.setattr(command, "detect", lambda *a, **k: found)
    assert main(["detect"]) == 0
    out = capsys.readouterr().out
    assert f"{laptop.chip} GPU — 18 GB, unified memory" in out
    assert f"Host: darwin {laptop.version} arm64" in out


def _scan_printed(
    document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> str:
    from mcgyvr.cli import main
    from mcgyvr.serving import rigscan

    monkeypatch.setattr(rigscan, "scan", lambda *a, **k: copy.deepcopy(document))
    assert main(["scan"]) == 0
    return capsys.readouterr().out


def test_scan_prints_the_system_the_backend_and_the_cpu_model(
    rigs: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    laptop = host_shape("unified-laptop")
    out = _scan_printed(host_scan_document(laptop), monkeypatch, capsys)
    assert f"System   darwin {laptop.version}, arm64" in out
    assert "(metal, unified memory, estimate)" in out
    assert f"CPU      {laptop.cpu_model}, 8 cores, 8 threads" in out


def test_scan_prints_a_cards_backend_on_windows(
    rigs: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    windows = host_shape("windows-one-card")
    out = _scan_printed(host_scan_document(windows), monkeypatch, capsys)
    assert "(cuda)" in out and "System   windows" in out


def test_scan_prints_a_memory_total_alone_without_anything_free(
    rigs: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = host_scan_document(host_shape("mac-without-unified"))
    document["memory"] = {"total_gb": 16.0, "available_gb": None}
    out = _scan_printed(document, monkeypatch, capsys)
    assert "  RAM      16.0 GB\n" in out
    assert "available" not in out.split("RAM", 1)[1].split("\n", 1)[0]
