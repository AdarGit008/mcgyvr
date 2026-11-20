"""Invented hardware tables and readings, for the tests of the capability record.

The table rows, card names, ids and figures here are made up and name no real
product; a test built on them promises how a reading meets a table, never what
the shipped table says. Rows are built as the loader builds them
(:class:`mcgyvr.hardware_table.Row` of :class:`~mcgyvr.hardware_table.Cell`), so
the three states of a cell are the loader's own.
"""

from __future__ import annotations

import datetime
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from mcgyvr.hardware_table import Cell, HardwareTable, Row, Source
from mcgyvr.scan import (
    Bandwidth,
    Cpu,
    CpuDetail,
    Device,
    Fact,
    Gpu,
    Host,
    Machine,
    Memory,
    Scan,
    Vram,
)

MIB_PER_GIB = 1024
BUILT = datetime.date(2026, 1, 3)
SOURCES = ("s1", "s2")
HOST = "box-a.example"


def cell(value: Any, source: str = "s1") -> Cell:
    """A cell a page gives (or, for False, [] or None, states is not there)."""
    return Cell(value=value, source=source, how="stated", official=True)


def row(row_id: str, vendor: str, kind: str, **cells: Any) -> Row:
    """A row whose cells are given as ``field=value`` with dots as ``__``; a value
    that is a :class:`Cell` is taken as it is."""
    made = {
        field.replace("__", "."): one if isinstance(one, Cell) else cell(one)
        for field, one in cells.items()
    }
    return Row(id=row_id, vendor=vendor, kind=kind, cells=MappingProxyType(made))


def table(*rows: Row) -> HardwareTable:
    sources: Mapping[str, Source] = MappingProxyType(
        {
            sid: Source(
                id=sid,
                url=f"https://vendor.example/{sid}",
                publisher="vendor.example",
                official=True,
                read=BUILT,
            )
            for sid in SOURCES
        }
    )
    return HardwareTable(built=BUILT, sources=sources, rows=rows)


def device(
    name: str | None,
    *,
    vendor: str = "nvidia",
    index: int = 0,
    total_mib: int | None = None,
    pci_device: str | None = None,
    kind: str = "gpu",
    backend: str = "cuda",
    **fields: Any,
) -> Device:
    """A card as the wider reading lists it, placed by vendor and index."""
    return Device(
        vendor=vendor,
        index=index,
        id=f"{vendor}:{index}",
        name=name,
        pci_device=pci_device,
        total_mib=total_mib,
        free_mib=total_mib,
        used_mib=None if total_mib is None else 0,
        kind=kind,
        backend=backend,
        figure="reading",
        **fields,
    )


def scan(
    *devices: Device,
    ram_gib: int | None = 64,
    cpu_model: str | None = "Acme Q9 7700 CPU @ 3.10GHz",
    bandwidth_gbps: float | None = 51.5,
    gpus: tuple[Gpu, ...] = (),
    wider: bool = True,
    flags: tuple[tuple[str, bool], ...] = (("avx2", True), ("avx512f", False)),
) -> Scan:
    """An invented reading. With ``wider`` it carries the device list and the CPU's
    flags and clock, as a reading asked for them does; without, it carries
    neither, as an older reader's or one not asked for them."""
    memory = None
    if ram_gib is not None:
        memory = Memory(total_gb=float(ram_gib), available_gb=float(ram_gib) - 4)
    return Scan(
        machine=Machine(id="id-a", host=HOST, kernel="6.1.0-example"),
        gpus=gpus,
        memory=memory,
        cpu=Cpu(cores=8, threads=16, model=cpu_model),
        bandwidth=(
            None
            if bandwidth_gbps is None
            else Bandwidth(measured_gbps=bandwidth_gbps, how="memcpy probe")
        ),
        facts=(
            Fact(field="memory.total_gb", how="/proc/meminfo MemTotal"),
            Fact(field="cpu.model", how="/proc/cpuinfo, else lscpu"),
            *(
                Fact(field=f"gpu[{one.index}].vram.total_mib", how="nvidia-smi")
                for one in gpus
            ),
        ),
        host=Host(os="linux", arch="x86_64", version="6.1.0-example"),
        devices=devices if wider else None,
        cpu_detail=(
            CpuDetail(
                flags=flags,
                flags_from="/proc/cpuinfo flags",
                max_mhz=4200,
                max_mhz_from="cpufreq cpuinfo_max_freq",
            )
            if wider
            else None
        ),
    )


def gpu(
    name: str,
    total_mib: int,
    *,
    index: int = 0,
    kind: str = "gpu",
    backend: str = "cuda",
) -> Gpu:
    """A sized card as a reading's ``gpus`` lists it."""
    return Gpu(
        index=index,
        name=name,
        vram=Vram(total_mib=total_mib, used_mib=0, free_mib=total_mib),
        kind=kind,
        backend=backend,
    )
