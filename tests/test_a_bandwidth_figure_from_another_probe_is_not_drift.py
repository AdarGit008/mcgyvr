"""A bandwidth figure another probe took is not a move of the hardware.

The scan's memory bandwidth figure names its probe in ``how``. A rig file
written by one probe (a single-thread copy) and a later reading by another (a
multi-threaded read) hold two figures that measure different things, so their
difference says nothing of the machine: :func:`mcgyvr.serving.rigfile.moved`
compares them only when one probe took both, and ``mcgyvr scan`` on unchanged
hardware exits 0. Two figures from one probe are compared as before, past
:data:`mcgyvr.serving.rigfile.BANDWIDTH_TOLERANCE`, and a move is hardware.

The machine is an invented one, its reading stubbed at the one reader.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.cli import main
from mcgyvr.exits import Exit
from mcgyvr.serving import rigfile

MACHINE_ID = "0a1b2c3d4e5f6a7b"
#: The ``how`` of the copy probe, as rig files written by it hold it.
COPY_HOW = "in-process copy of 256 MiB x5, best pass, bytes copied/s"
#: The ``how`` of the read probe, with a copy figure of its own appended.
READ_HOW = (
    "multi-threaded read of 256 MiB x8 threads, best of 5 passes, bytes read/s; "
    "copy 14.1 GB/s"
)
#: The read probe again, run with another block and thread count.
READ_HOW_SMALL = (
    "multi-threaded read of 64 MiB x4 threads, best of 5 passes, bytes read/s"
)


def _reading(gbps: float, how: str) -> dict[str, Any]:
    """The one reader's document for the invented machine, bandwidth as given."""
    return {
        "machine": {"id": MACHINE_ID, "host": "bench-host", "kernel": "6.8.0-x"},
        "gpus": [],
        "memory": {"total_gb": 47.0, "available_gb": 28.6},
        "cpu": {"cores": 10, "threads": 20},
        "bandwidth": {"measured_gbps": gbps, "how": how},
        "disk": {"path": "/home/user/.cache/mcgyvr/weights", "free_gb": 900.0},
        "models_on_disk": [],
        "docker": None,
        "network": {"reached_at": None, "ipv4": []},
        "snapshot": {"kernel": "6.8.0-x"},
        "notes": [],
        "facts": [],
    }


#: Records a reading of the invented machine, then compares the next one with it.
Compare = Callable[[tuple[float, str], tuple[float, str]], tuple[rigfile.Moved, ...]]


@pytest.fixture
def rigs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "rigs"
    monkeypatch.setenv("MCGYVR_RIGS", str(folder))
    return folder


@pytest.fixture
def compare(rigs: Path) -> Compare:
    def run(
        was: tuple[float, str], now: tuple[float, str]
    ) -> tuple[rigfile.Moved, ...]:
        rigfile.save(rigfile.LOCAL, _reading(*was))
        saved = rigfile.save(rigfile.LOCAL, _reading(*now))
        assert saved.before is not None
        return rigfile.moved(saved.before, saved.now)

    return run


def test_the_method_is_the_probe_named_before_of(rigs: Path) -> None:
    def method(how: str) -> str:
        return rigfile.from_reading(rigfile.LOCAL, _reading(1.0, how)).bandwidth_method

    assert method(COPY_HOW) == "in-process copy"
    assert method(READ_HOW) == "multi-threaded read"
    assert method(READ_HOW_SMALL) == "multi-threaded read"
    assert method("") == ""


def test_a_copy_figure_against_a_read_figure_is_not_a_move(compare: Compare) -> None:
    assert compare((13.6, COPY_HOW), (33.9, READ_HOW)) == ()


def test_one_probe_past_the_tolerance_is_a_hardware_move(compare: Compare) -> None:
    found = compare((20.0, READ_HOW), (30.0, READ_HOW_SMALL))
    assert found == (rigfile.Moved("bandwidth_gbps", 20.0, 30.0),)
    assert all(rigfile.is_hardware(change) for change in found)


def test_one_probe_within_the_tolerance_is_not_a_move(compare: Compare) -> None:
    assert compare((20.0, READ_HOW), (22.0, READ_HOW)) == ()


@pytest.mark.parametrize(
    ("was_how", "now_how"), [("", READ_HOW), (READ_HOW, ""), ("", "")]
)
def test_a_figure_without_its_probe_is_not_compared(
    compare: Compare, was_how: str, now_how: str
) -> None:
    assert compare((20.0, was_how), (30.0, now_how)) == ()


def _scan_reads(monkeypatch: pytest.MonkeyPatch, gbps: float, how: str) -> None:
    from mcgyvr.serving import rigscan

    monkeypatch.setattr(rigscan, "machine_id", lambda **_: MACHINE_ID)
    monkeypatch.setattr(rigscan, "scan", lambda *a, **k: _reading(gbps, how))


def test_scan_after_the_probe_changed_exits_zero(
    rigs: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _scan_reads(monkeypatch, 13.6, COPY_HOW)
    assert main(["scan"]) == Exit.OK
    _scan_reads(monkeypatch, 33.9, READ_HOW)
    capsys.readouterr()
    assert main(["scan"]) == Exit.OK
    assert "bandwidth_gbps" not in capsys.readouterr().out


def test_scan_with_one_probe_past_the_tolerance_exits_four(
    rigs: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _scan_reads(monkeypatch, 20.0, READ_HOW)
    assert main(["scan"]) == Exit.OK
    _scan_reads(monkeypatch, 30.0, READ_HOW)
    capsys.readouterr()
    assert main(["scan"]) == Exit.MISMATCH
    assert "bandwidth_gbps 20.0 -> 30.0" in capsys.readouterr().out
