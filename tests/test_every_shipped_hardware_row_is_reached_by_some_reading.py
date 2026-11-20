"""Every shipped hardware row is reached by some reading, and only by its own.

For each row of the shipped table a reading is made from the row itself. Where
the product's reader fixes the form of what it prints, the reading takes that
form: a card's PCI device id in lower case with ``0x`` before it, as sysfs and
the tools print it, and a Mac's GPU as a chip name with `` GPU`` after it. Where
the form comes from the machine (an AMD card's name from its tool, a CPU's model
string), the reading is the table's own name or listed model, after the vendor's
name where the model lacks it. So what this proves is that every row is reached
from the table's own id or name through the cleaning rule, not that every real
tool's spelling is.

Each reading's record names the row among its candidates, and every candidate is
the row's like: of its vendor, and listing the same id, carrying the same name
key, or listing a model the reading holds. A row no reading can reach is found
when the table is built, not when a user's machine is read, and a name that also
meets a row it only begins is found too.
"""

from __future__ import annotations

import pytest

from mcgyvr import machine_capability
from mcgyvr.hardware_table import VALUE, Row, shipped_table
from mcgyvr.machine_capability import card_key, cpu_words
from mcgyvr.scan import Device
from tests.invented_hardware import MIB_PER_GIB, device, scan

VENDOR_WORD = {"intel": "Intel", "amd": "AMD", "nvidia": "NVIDIA", "apple": "Apple"}
BACKEND = {"nvidia": "cuda", "amd": "rocm", "intel": "vulkan"}


def _value(row: Row, field: str) -> object:
    found = row.cell(field)
    return found.value if found.state == VALUE else None


def _listed(row: Row, field: str) -> list[object]:
    found = _value(row, field)
    return list(found) if isinstance(found, list) else []


def _id(printed: object) -> str:
    return str(printed).lower().removeprefix("0x")


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
                pci_device=f"0x{_id(one)}",
            )
            for one in ids
        ]
    name = str(_value(row, "name"))
    return [device(name, vendor=vendor, backend=backend, total_mib=mib)]


def _cpu_name(row: Row, model: object) -> str:
    """The listed model, after the vendor's name unless it holds it already: the
    reader keeps the machine's own model string, and a CPU's vendor is known by
    its name."""
    text = str(model)
    if row.vendor in text.lower().split():
        return text
    return f"{VENDOR_WORD[row.vendor]} {text}"


#: A reading made from a row, by what it was matched on (``id``, ``name`` or
#: ``cpu``), with the facts its record gives.
Reached = tuple[str, str, machine_capability.TableFacts]


def _reached(row: Row) -> list[Reached]:
    table = shipped_table()
    if row.kind == "gpu":
        return [
            (
                "id" if one.pci_device else "name",
                one.pci_device or str(one.name),
                machine_capability.of_scan(scan(one), table).cards[0].table,
            )
            for one in _card_readings(row)
        ]
    if row.kind == "soc":
        sizes = _value(row, "memory.sizes_gb")
        gpu = device(
            f"{_value(row, 'name')} GPU",
            vendor="apple",
            kind="unified",
            backend="metal",
            total_mib=1,
        )
        return [
            (
                "name",
                str(gpu.name),
                machine_capability.of_scan(scan(gpu, ram_gib=gb), table).cards[0].table,
            )
            for gb in (sizes if isinstance(sizes, list) else [None])
        ]
    models = _value(row, "models")
    assert isinstance(models, list), row.id
    found: list[Reached] = []
    for model in models:
        name = _cpu_name(row, model)
        record = machine_capability.of_scan(scan(cpu_model=name), table)
        found.append(("cpu", name, record.cpu.table))
    return found


def _held(words: tuple[str, ...], inside: tuple[str, ...]) -> bool:
    span = len(words)
    return any(inside[at : at + span] == words for at in range(len(inside) - span + 1))


def _alike(on: str, said: str, other: Row) -> bool:
    """Whether ``other`` carries what a reading matched on ``on`` said: the same
    PCI device id, the same name key, or a listed model the CPU name holds."""
    if on == "id":
        return _id(said) in {_id(one) for one in _listed(other, "pci_device_ids")}
    if on == "cpu":
        words = cpu_words(said)
        models = _listed(other, "models")
        return any(_held(cpu_words(str(one)), words) for one in models)
    return card_key(str(_value(other, "name"))) == card_key(said)


@pytest.mark.parametrize("row", shipped_table().rows, ids=lambda one: one.id)
def test_every_shipped_row_is_a_candidate_of_a_reading_made_from_it(row: Row) -> None:
    found = _reached(row)
    assert found, row.id
    for on, said, facts in found:
        assert row.id in facts.rows, (row.id, facts.why)
        for one in facts.rows:
            other = shipped_table().row(one)
            assert other is not None, one
            assert other.vendor == row.vendor, (row.id, other.id)
            assert _alike(on, said, other), (row.id, other.id, facts.why)


def test_the_vendors_whose_cards_carry_ids_are_matched_by_their_ids() -> None:
    by: dict[str, set[str | None]] = {}
    for row in shipped_table().rows:
        if row.kind == "gpu":
            for _, _, facts in _reached(row):
                by.setdefault(row.vendor, set()).add(facts.by)
    assert by == {
        "nvidia": {machine_capability.BY_PCI_ID},
        "intel": {machine_capability.BY_PCI_ID},
        "amd": {machine_capability.BY_NAME},
    }
