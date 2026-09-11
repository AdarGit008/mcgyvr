"""A rig is its host, hardware and system.

RED. ``mcgyvr.fleet.rig`` does not exist, and the two functions that answer
"which OS install is this" are both still called ``machine_id``. The intent is
``records/plans/fleet-identity.md`` §1.

Owner's ruling: any hardware or system change mints a new ``rig_id``. That
inverts ``src/mcgyvr/scan.py:642`` ("never by what was measured"), on purpose:
RAM moved between srv1 and srv2 twice in six days, and a BIOS reset took PL1
from 95 W to 4095 W, and every artifact from those windows was internally
consistent and wrong (``tools/runs/hosts.json`` ``_rig_doc``). A new name makes
every lock on the old one lapse, loudly.

Whether the card reserve (``gpu_reserve_mib``) belongs in the name is open
(plan §12). Gate 2 compares it literally with ``tools/runs/hosts.json``, and the
±3 MiB it is said to move across boots has not been read on two boots of either
rig. That reading belongs to ``red/fleet-identity-measurements``, so no test
here pins it either way.
"""

from __future__ import annotations

import importlib
from typing import Any

from tests.red_port.conftest import required

#: srv1 as ``tools/runs/hosts.json`` declares it, plus the system facts the
#: snapshot does not read yet.
HW: dict[str, Any] = {
    "cpu_model": "Intel(R)_Core(TM)_i5-9600K_CPU_@_3.70GHz",
    "cpu_max_mhz": "4600",
    "ram_mt_s": "3600",
    "pl1_uw": "95000000",
    "pl2_uw": "120000000",
    "gpu_name": "NVIDIA_GeForce_GTX_1660_SUPER",
    "gpu_vram_mib": "6144",
    "gpu_cc": "7.5",
    "mem_total_kib": "15700000",
}
SYSTEM: dict[str, Any] = {
    "driver": "580.173.02",
    "docker": "29.7.2",
    "kernel": "6.8.0-139-generic",
    "swap_total_kib": "8388604",
    "swappiness": "60",
}


def _rig_id() -> Any:
    return required(
        "name a rig by its host, hardware and system",
        lambda: importlib.import_module("mcgyvr.fleet.rig").rig_id,
    )


def test_a_driver_bump_mints_a_new_rig() -> None:
    rig_id = _rig_id()
    base = rig_id("srv1", HW, SYSTEM)
    assert base.startswith("rig-")
    assert rig_id("srv1", HW, {**SYSTEM, "driver": "580.173.03"}) != base


def test_a_bios_reset_mints_a_new_rig() -> None:
    """PL1 read 95 W at 05:23 and 4095 W at 05:57 after a hard lock (hosts.json)."""
    rig_id = _rig_id()
    base = rig_id("srv1", HW, SYSTEM)
    assert rig_id("srv1", {**HW, "pl1_uw": "4095000000"}, SYSTEM) != base
    assert rig_id("srv1", {**HW, "cpu_max_mhz": "4800"}, SYSTEM) != base


def test_the_host_is_part_of_the_rig() -> None:
    rig_id = _rig_id()
    assert rig_id("srv1", HW, SYSTEM) != rig_id("srv2", HW, SYSTEM)


def test_the_scan_names_the_os_install_os_machine_id() -> None:
    """Two functions share ``machine_id`` and return different values.

    ``scan.py:894`` is a sha256[:16] of ``/etc/machine-id``; ``gatelib.py:388``
    is its raw first 12 characters. Neither is a rig, and a reader holding a
    ``rig_id`` must not find a ``machine_id`` beside it that means something else.
    """
    scan = importlib.import_module("mcgyvr.scan")
    required(
        "name the OS install os_machine_id in the scan", lambda: scan.os_machine_id
    )
    assert not hasattr(scan, "machine_id"), "machine_id must be gone, not aliased"


def test_the_door_names_the_os_install_os_machine_id() -> None:
    gatelib = importlib.import_module("mcgyvr.serving.gatelib")
    required(
        "name the OS install os_machine_id in the door's gate library",
        lambda: gatelib.os_machine_id,
    )
    assert not hasattr(gatelib, "machine_id"), "machine_id must be gone, not aliased"
