"""A scan reads /proc/meminfo and the CPU model once, and every section takes that read.

The memory section, the bandwidth probe's block size and the snapshot's
``mem_*_kib`` keys come from one read of /proc/meminfo; the CPU section and the
snapshot's ``cpu_model`` from one look-up of the model (/proc/cpuinfo, else
lscpu). A fallback added to one of them then reaches the others, and a scan
does not see two moments of a meminfo that changes while it runs.
"""

from __future__ import annotations

import collections
import tempfile
from typing import Any
from unittest import mock

import pytest

from mcgyvr.serving import rigscan
from tests import machine_shapes


def _scan(
    meminfo: str | None = None,
) -> tuple[dict[str, Any], collections.Counter[str]]:
    machine = next(m for m in machine_shapes.host_shapes() if m.system == "linux")
    reads: collections.Counter[str] = collections.Counter()
    real = rigscan._read
    spare: list[int | None] = []

    def read(root: str, path: str) -> tuple[str | None, str]:
        reads[path] += 1
        return real(root, path)

    def probe(spare_mib: int | None = None) -> None:
        spare.append(spare_mib)

    with (
        machine_shapes._host_root(machine) as root,
        machine_shapes._host_tools(machine),
        tempfile.TemporaryDirectory() as weights,
    ):
        if meminfo is not None:
            with open(root + "/proc/meminfo", "w", encoding="utf-8") as handle:
                handle.write(meminfo)
        with (
            mock.patch.object(rigscan, "_read", read),
            mock.patch.object(rigscan, "measure_bandwidth", probe),
        ):
            document = rigscan.scan(weights, root=root, system="linux")
    document["spare"] = spare
    return document, reads


def test_meminfo_and_cpuinfo_are_each_read_once_per_scan() -> None:
    document, reads = _scan()
    assert reads["/proc/meminfo"] == 1
    assert reads["/proc/cpuinfo"] == 1
    assert document["snapshot"]["cpu_model"]
    assert document["cpu"]["model"]


@pytest.mark.parametrize(
    ("meminfo", "spare"),
    [
        ("MemTotal: 8388608 kB\nMemAvailable: 3145728 kB\n", 3072),
        ("MemTotal: 8388608 kB\nMemFree: 1048576 kB\n", 1024),
    ],
)
def test_the_probe_and_the_snapshot_take_the_memory_sections_read(
    meminfo: str, spare: int
) -> None:
    """MemAvailable, else MemFree: the one rule, the probe sized by it."""
    document, _ = _scan(meminfo)
    assert document["spare"] == [spare]
    assert document["memory"]["available_gb"] == round(spare / 1024, 1)
    available = document["snapshot"].get("mem_available_kib")
    assert available == ("3145728" if "MemAvailable" in meminfo else None)
    assert document["snapshot"]["mem_total_kib"] == "8388608"


@pytest.mark.parametrize(
    ("spare_mib", "block"),
    [(None, rigscan.COPY_MIB_TIGHT), (2559, rigscan.COPY_MIB_TIGHT), (2560, 256)],
)
def test_the_probe_takes_the_small_block_below_two_and_a_half_gb_spare(
    spare_mib: int | None, block: int
) -> None:
    """2 GB to spare beyond two 256 MiB buffers, counted in whole MiB as the
    reading counts them; memory not seen is a small machine's."""
    assert rigscan.COPY_MIB == 256
    with mock.patch.object(rigscan, "bytearray", create=True) as made:
        made.side_effect = MemoryError
        assert rigscan.measure_bandwidth(spare_mib) is None
    assert made.call_args_list[0].args == (block * rigscan.MIB_BYTES,)
