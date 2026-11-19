"""A reading without the wider fields reads them as unknown.

A rig whose reader is older prints no ``devices`` and no ``cpu_detail``. Such a
reading parses as before: the scan holds None for both, which is unknown, not
"no card" and not "no flag", and ``--hardware`` says the reading carries them
not. A field of the wrong type reads as unknown too, never as an error, and a
flag the system did not answer for is unknown, never absent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.machine_shapes import host_scan_document, host_shape


def _older(label: str, document: dict[str, Any] | None = None) -> dict[str, Any]:
    """A reading as an older reader prints it: without the wider fields."""
    if document is None:
        document = host_scan_document(host_shape(label), wider=True)
    return {k: v for k, v in document.items() if k not in ("devices", "cpu_detail")}


def _scan(document: dict[str, Any]) -> Any:
    from mcgyvr.scan import Scan

    return Scan.from_json(json.dumps(document))


@pytest.mark.parametrize(
    "label", ["linux-one-card", "unified-laptop", "windows-other-gpu"]
)
def test_an_older_readers_scan_parses_with_its_wider_fields_unknown(
    label: str,
) -> None:
    document = host_scan_document(host_shape(label), wider=True)
    scan = _scan(_older(label, document))
    assert scan.devices is None
    assert scan.cpu_detail is None
    whole = _scan(document)
    assert scan.gpus == whole.gpus
    assert scan.to_json() == whole.to_json()
    printed = json.loads(scan.to_json(hardware=True))
    assert printed["devices"] is None and printed["cpu_detail"] is None


def test_an_older_rig_file_is_read_as_before(tmp_path: Path) -> None:
    from mcgyvr.serving import rigfile

    payload = {"rig": "box-1", "read_at": "2026-01-01T00:00:00Z"}
    text = json.dumps({**payload, "reading": _older("linux-one-card")})
    rig = rigfile.from_json(text)
    assert rig.scan.devices is None and rig.scan.cpu_detail is None


def test_hardware_says_an_older_reading_carries_no_wider_fields() -> None:
    from mcgyvr.cli.commands.machine import _hardware_lines

    lines = _hardware_lines(_scan(_older("linux-one-card")))
    assert lines == [
        "  Devices  not in this reading (an older reader)",
        "  CPU ISA  not in this reading (an older reader)",
    ]


def test_a_wider_field_of_the_wrong_type_reads_as_unknown() -> None:
    document = _older("linux-one-card")
    document["devices"] = [
        {"vendor": "amd", "index": 0, "total_mib": "12", "pci_device": 7},
        {"index": 1},
        {"vendor": "intel", "index": True},
        "a card",
    ]
    document["cpu_detail"] = {
        "flags": {"avx2": True, "avx512f": False, "amx_int8": "yes"},
        "max_mhz": "4200",
        "flags_from": 3,
    }
    scan = _scan(document)
    assert scan.devices is not None and len(scan.devices) == 1
    (device,) = scan.devices
    assert (device.vendor, device.index) == ("amd", 0)
    assert device.total_mib is None and device.pci_device is None
    detail = scan.cpu_detail
    assert detail is not None
    assert detail.has("avx2") is True
    assert detail.has("avx512f") is False
    assert detail.has("amx_int8") is None
    assert detail.has("avx_vnni") is None
    assert detail.max_mhz is None and detail.flags_from is None


@pytest.mark.parametrize("value", ["cards", 3, {"vendor": "amd"}])
def test_a_device_list_that_is_not_a_list_is_unknown(value: object) -> None:
    document = _older("linux-one-card")
    document["devices"] = value
    document["cpu_detail"] = "fast"
    scan = _scan(document)
    assert scan.devices is None and scan.cpu_detail is None
