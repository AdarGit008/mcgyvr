"""Readers that parse the text the rig prints, so an observation can be filed.

Each reader turns fixture text (``/proc/meminfo``, ``/proc/vmstat``,
``nvidia-smi --query-compute-apps`` and ``/proc/<pid>/cgroup``) into the MiB or
count fields an observation or a live admission reads. Nothing here reaches a
rig: the parsing is pinned on text, and the contact is the caller's.
(``records/plans/fleet-identity.md`` §6 and §7.)
"""

from __future__ import annotations

import re

#: ``0::/system.slice/docker-<64-hex>.scope`` — a container's cgroup carries its
#: 64-character id after ``docker-``. Anything else is a process we did not start.
_DOCKER_ID = re.compile(r"docker-([0-9a-f]{64})\.scope")


def parse_meminfo(text: str) -> dict[str, float]:
    """``/proc/meminfo`` kB figures as MiB, keyed by what an observation reads."""
    wanted = {
        "MemTotal": "mem_total_mib",
        "MemAvailable": "mem_available_mib",
        "Shmem": "shmem_mib",
        "SwapTotal": "swap_total_mib",
        "SwapFree": "swap_free_mib",
    }
    out: dict[str, float] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        key = wanted.get(parts[0].rstrip(":"))
        if key is None:
            continue
        out[key] = int(parts[1]) / 1024.0
    return out


def parse_vmstat(text: str) -> dict[str, int]:
    """``/proc/vmstat`` counters an observation records and never alerts."""
    out: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] in ("pswpout", "pswpin", "pgmajfault"):
            out[parts[0]] = int(parts[1])
    return out


def _container(cgroup: str) -> str | None:
    match = _DOCKER_ID.search(cgroup)
    return match.group(1) if match else None


def card_by_container(apps: str, pid_cgroup: dict[int, str]) -> dict[str, int]:
    """Card use per container, with what no container owns summed as ``foreign``.

    ``apps`` is ``nvidia-smi --query-compute-apps=pid,used_memory``'s
    ``pid, used_memory`` rows (memory in MiB). ``pid_cgroup`` maps each pid to
    its ``/proc/<pid>/cgroup`` line. A pid whose cgroup names no ``docker-``
    container is a process live did not start and must not kill, so it is
    attributed to ``foreign``.
    """
    by: dict[str, int] = {}
    for line in apps.splitlines():
        parts = line.split(",")
        if len(parts) < 2:
            continue
        pid, mem = int(parts[0].strip()), int(parts[1].strip())
        cgroup = pid_cgroup.get(pid, "")
        name = _container(cgroup) if cgroup else None
        key = name if name is not None else "foreign"
        by[key] = by.get(key, 0) + mem
    return by
