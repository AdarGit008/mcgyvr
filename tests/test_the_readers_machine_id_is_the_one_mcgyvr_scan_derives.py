"""The reader's machine id is the one ``mcgyvr scan`` derives, when well formed.

For a machine-id file of one line, and for a machine with no machine-id file
and a plain host name, the reader and ``mcgyvr scan`` name the machine by the
same id. Where their inputs are not well formed they differ, and
:mod:`mcgyvr.fleet.machine` says how.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from tests.machinereader import Staged, run


def _scan_id(files: tuple[Path, ...], node: str) -> str:
    from mcgyvr import scan

    with (
        mock.patch.object(scan, "MACHINE_ID_FILES", files),
        mock.patch("platform.node", lambda: node),
        mock.patch("platform.release", lambda: "0.0.0-example"),
    ):
        machine, _, _ = scan._scan_machine()
    return machine.id


def _root(where: Path) -> Path:
    return where / "root"


@pytest.mark.parametrize(
    "content", ["0123456789abcdef0123456789abcdef", "  fedcba9876543210fedcba98  "]
)
def test_a_machine_id_file_gives_the_id_scan_gives(
    content: str, tmp_path: Path
) -> None:
    from mcgyvr.fleet import machine

    reading = machine.parse(run(Staged(machine_id_file=content), tmp_path).stdout)
    files = (_root(tmp_path) / "etc" / "machine-id",)
    assert reading.machine_id == _scan_id(files, "box-1.example")


def test_the_host_name_fallback_gives_the_id_scan_gives(tmp_path: Path) -> None:
    from mcgyvr.fleet import machine

    staged = Staged(machine_id_file=None, hostname="box-8.example")
    reading = machine.parse(run(staged, tmp_path).stdout)
    missing = (_root(tmp_path) / "etc" / "machine-id",)
    assert reading.machine_id_from == "hostname"
    assert reading.machine_id == _scan_id(missing, "box-8.example")
