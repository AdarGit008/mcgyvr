"""Every shipped hardware row is reached by some reading.

For each row of the shipped table a reading is made the way a reader would
print that device: a card with each PCI device id the row lists (lower case,
``0x`` before it, as sysfs and the tools print them), else with its name; a
Mac's GPU as its chip's name with ``Apple`` before it and ``GPU`` after, on each
RAM size the row states; a CPU as each model the row lists, after its vendor's
name. Each reading's record names the row among its candidates, so a row no
reading can reach is found when the table is built, not when a user's machine
is read. A card matched by its id or its name keeps every candidate its own
reading names, and none of another vendor.
"""

from __future__ import annotations

import pytest

from mcgyvr import machine_capability
from mcgyvr.hardware_table import VALUE, Row, shipped_table
from mcgyvr.scan import Device
from tests.invented_hardware import MIB_PER_GIB, device, scan

VENDOR_WORD = {"intel": "Intel", "amd": "AMD", "nvidia": "NVIDIA", "apple": "Apple"}
BACKEND = {"nvidia": "cuda", "amd": "rocm", "intel": "vulkan"}


def _value(row: Row, field: str) -> object:
    found = row.cell(field)
    return found.value if found.state == VALUE else None


def _card_readings(row: Row) -> list[Device]:
    size = _value(row, "memory.size_gb")
    mib = round(float(size) * MIB_PER_GIB) if isinstance(size, int | float) else None
    ids = _value(row, "pci_device_ids")
    vendor, backend = row.vendor, BACKEND[row.vendor]
    if isinstance(ids, list):
        return [
            device(
                None,
                vendor=vendor,
                backend=backend,
                total_mib=mib,
                pci_device=f"0x{str(one).lower().removeprefix('0x')}",
            )
            for one in ids
        ]
    name = f"{VENDOR_WORD[vendor]} {_value(row, 'name')}"
    return [device(name, vendor=vendor, backend=backend, total_mib=mib)]


def _reached(row: Row) -> list[machine_capability.TableFacts]:
    table = shipped_table()
    if row.kind == "gpu":
        return [
            machine_capability.of_scan(scan(one), table).cards[0].table
            for one in _card_readings(row)
        ]
    if row.kind == "soc":
        sizes = _value(row, "memory.sizes_gb")
        gpu = device(
            f"Apple {_value(row, 'name')} GPU",
            vendor="apple",
            kind="unified",
            backend="metal",
            total_mib=1,
        )
        return [
            machine_capability.of_scan(scan(gpu, ram_gib=gb), table).cards[0].table
            for gb in (sizes if isinstance(sizes, list) else [None])
        ]
    models = _value(row, "models")
    assert isinstance(models, list), row.id
    return [
        machine_capability.of_scan(
            scan(cpu_model=f"{VENDOR_WORD[row.vendor]} {model}"), table
        ).cpu.table
        for model in models
    ]


@pytest.mark.parametrize("row", shipped_table().rows, ids=lambda one: one.id)
def test_every_shipped_row_is_a_candidate_of_a_reading_made_from_it(row: Row) -> None:
    found = _reached(row)
    assert found, row.id
    for facts in found:
        assert row.id in facts.rows, (row.id, facts.why)
        rows = [shipped_table().row(one) for one in facts.rows]
        vendors = {one.vendor for one in rows if one is not None}
        assert vendors == {row.vendor}, (row.id, facts.rows)


def test_the_vendors_whose_cards_carry_ids_are_matched_by_their_ids() -> None:
    by: dict[str, set[str | None]] = {}
    for row in shipped_table().rows:
        if row.kind == "gpu":
            for facts in _reached(row):
                by.setdefault(row.vendor, set()).add(facts.by)
    assert by == {
        "nvidia": {machine_capability.BY_PCI_ID},
        "intel": {machine_capability.BY_PCI_ID},
        "amd": {machine_capability.BY_NAME},
    }
