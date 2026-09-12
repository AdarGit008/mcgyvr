"""The readers an observation stands on parse the text the rig prints.

RED. ``mcgyvr.fleet.observe`` does not exist; ``src/`` reads ``MemAvailable``
(``src/mcgyvr/scan.py``) and whole-card used/free (``servelib.card``) and
nothing else. The intent is ``records/plans/fleet-identity.md`` §6 and §7.

Swap, major faults and Shmem are recorded beside every observation (they
explain a warm-decode alert and are never alerted themselves), and card use
attributed per container is how live tells a unit of ours from a process it did
not start, which refuses the rig. Every figure was readable in the campaign:
per-process card with the pid mapped to its container through
``/proc/<pid>/cgroup`` (Q15), Shmem and swap and faults (Q7). These tests pin
the parsing on fixture text, so no test reaches a rig.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from tests.red_port.conftest import required

MEMINFO = """MemTotal:       15700000 kB
MemAvailable:   14534568 kB
Shmem:           7831552 kB
SwapTotal:       8388604 kB
SwapFree:        7209000 kB
"""
VMSTAT = "pgmajfault 188000\npswpin 1200\npswpout 565534\n"
APPS = "4242, 6816\n4343, 3810\n999, 3374\n"
DOCKER_A = "0::/system.slice/docker-" + "a" * 64 + ".scope\n"
DOCKER_B = "0::/system.slice/docker-" + "b" * 64 + ".scope\n"


def _observe() -> Any:
    return required(
        "read card, RAM, swap and faults from the text the rig prints",
        lambda: importlib.import_module("mcgyvr.fleet.observe"),
    )


def test_meminfo_gives_available_shmem_and_swap_in_mib() -> None:
    read = _observe().parse_meminfo(MEMINFO)
    assert read["mem_available_mib"] == pytest.approx(14534568 / 1024)
    assert read["shmem_mib"] == pytest.approx(7831552 / 1024)
    assert read["swap_free_mib"] == pytest.approx(7209000 / 1024)
    assert read["swap_total_mib"] == pytest.approx(8388604 / 1024)


def test_vmstat_gives_swap_out_and_major_faults() -> None:
    read = _observe().parse_vmstat(VMSTAT)
    assert read["pswpout"] == 565534
    assert read["pgmajfault"] == 188000


def test_card_use_is_attributed_per_container_and_the_rest_is_foreign() -> None:
    """3,374 MiB held by a process that is not ours is srv1's 2026-09-04 reading."""
    by = _observe().card_by_container(
        APPS, {4242: DOCKER_A, 4343: DOCKER_B, 999: "0::/user.slice/session-2.scope\n"}
    )
    assert by == {"a" * 64: 6816, "b" * 64: 3810, "foreign": 3374}
