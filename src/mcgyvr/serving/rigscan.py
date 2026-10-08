#!/usr/bin/env python3
"""The read-only rig scan, shipped to a rig over ssh as ``python3 -``.

This is the one copy of the far-end scan. It must stay importable (the door
reads it by file to base64-encode it) and stdlib-only (the rig has no venv, no
mcgyvr, no PYTHONPATH). It measures the machine it runs on — cards via
nvidia-smi, RAM via /proc/meminfo, CPU via os.cpu_count, bandwidth by a timed
copy, free disk where weights would land, the version of the rig's own
docker daemon, and where it is reached: the address its ssh session arrived
at and every IPv4 address on its interfaces — and prints the same JSON shape
:meth:`mcgyvr.scan.Scan.from_json` parses.

Run as a module or as ``python3 -``: under ``__main__`` it prints one JSON
document to stdout and nothing else.
"""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
from typing import Any

NVIDIA_SMI_QUERY = "index,name,memory.total,memory.used,memory.free"
KB_PER_GB = 1024.0 * 1024.0
MIB_PER_GB = 1024.0
BYTES_PER_GB = 1024.0**3

COPY_MIB = 256
COPY_PASSES = 5
COPY_MIB_TIGHT = 64
TIGHT_RAM_GB = 2.0

WEIGHTS_DIR_ENV = "MCGYVR_WEIGHTS"
MACHINE_ID_FILES = ("/etc/machine-id", "/var/lib/dbus/machine-id")

#: What the rig's own docker CLI is asked: the daemon's version, one line.
DOCKER_VERSION_FORMAT = "{{.Server.Version}}"

#: What sshd tells the session it starts: the client's address and port,
#: then the address and port this machine was reached at.
SSH_CONNECTION_ENV = "SSH_CONNECTION"
#: What the rig's own ``ip`` is asked: every IPv4 address, one line each.
IP_ADDR_ARGS = ("-4", "-o", "addr", "show")

GPU_NOT_DETERMINED = "GPU: not determined"
GPU_ROW_UNREAD = "GPU: nvidia-smi printed a row this could not read"


def _run(binary: str, *args: str, timeout: float = 30.0) -> str | None:
    """Run a tool, returning its stdout or None if it cannot be run."""
    if shutil.which(binary) is None:
        return None
    try:
        done = subprocess.run(
            [binary, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _read_meminfo() -> str | None:
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def _free_bytes(path: str) -> int:
    """Free bytes on the filesystem holding ``path``, or the nearest ancestor."""
    probe = path
    while True:
        try:
            return shutil.disk_usage(probe).free
        except OSError:
            parent = os.path.dirname(probe)
            if parent == probe:
                return 0
            probe = parent


def _field(text: str, key: str) -> str | None:
    for line in text.splitlines():
        name, sep, rest = line.partition(":")
        if sep and name.strip() == key:
            return rest.strip()
    return None


def _int_field(text: str, key: str) -> int | None:
    value = _field(text, key)
    if value is None:
        return None
    head = value.split()[0] if value.split() else ""
    try:
        return int(head)
    except ValueError:
        return None


def _kb_field(text: str, key: str) -> float | None:
    value = _int_field(text, key)
    return None if value is None else float(value)


def _spare_gb() -> float:
    text = _read_meminfo()
    if text is None:
        return 0.0
    available = _kb_field(text, "MemAvailable")
    if available is None:
        available = _kb_field(text, "MemFree")
    return 0.0 if available is None else available / KB_PER_GB


def measure_bandwidth() -> dict[str, Any] | None:
    """Time a large memory copy and report GB/s, or None when it cannot be read."""
    mib = COPY_MIB
    if _spare_gb() < TIGHT_RAM_GB + 2 * mib / MIB_PER_GB:
        mib = COPY_MIB_TIGHT
    try:
        source = bytearray(mib * 1024 * 1024)
        target = bytearray(mib * 1024 * 1024)
    except (MemoryError, ValueError):
        return None
    target[:] = source  # fault both mappings in, off the clock
    moved = float(len(source))
    fastest = 0.0
    for _ in range(COPY_PASSES):
        start = time.perf_counter()
        target[:] = source
        elapsed = time.perf_counter() - start
        if elapsed > 0.0:
            fastest = max(fastest, moved / elapsed)
    if fastest <= 0.0:
        return None
    return {
        "measured_gbps": round(fastest / 1e9, 1),
        "how": (
            f"in-process copy of {mib} MiB x{COPY_PASSES}, best pass, bytes copied/s"
        ),
    }


def _fingerprint(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _scan_machine() -> tuple[
    dict[str, Any],
    tuple[dict[str, str], ...],
    tuple[str, ...],
]:
    """Identify the machine by something durable, as ``mcgyvr.scan`` does."""
    host = platform.node() or "localhost"
    kernel = platform.release()
    for path in MACHINE_ID_FILES:
        try:
            with open(path, encoding="utf-8") as fh:
                seed = fh.read().strip()
        except OSError:
            continue
        if seed:
            machine = {"id": _fingerprint(seed), "host": host, "kernel": kernel}
            return (
                machine,
                ({"field": "machine.id", "how": f"sha256 of {path}"},),
                (),
            )
    machine = {"id": _fingerprint(f"host:{host}"), "host": host, "kernel": kernel}
    return (
        machine,
        ({"field": "machine.id", "how": "sha256 of hostname"},),
        (
            "Machine id: derived from the hostname — no /etc/machine-id. It is "
            "stable until the host is renamed, and a rename will read as a new "
            "machine rather than as a changed one.",
        ),
    )


def _parse_gpu_row(line: str) -> dict[str, Any] | None:
    parts = [part.strip() for part in line.split(",")]
    if len(parts) < 5:
        return None
    try:
        index = int(parts[0])
        total, used, free = int(parts[-3]), int(parts[-2]), int(parts[-1])
    except ValueError:
        return None
    return {
        "index": index,
        "name": ", ".join(parts[1:-3]),
        "vram": {
            "total_mib": total,
            "used_mib": used,
            "free_mib": free,
            "reserved_mib": max(total - used - free, 0),
        },
    }


def _scan_gpus() -> tuple[
    tuple[dict[str, Any], ...],
    tuple[dict[str, str], ...],
    tuple[str, ...],
]:
    how = f"nvidia-smi --query-gpu={NVIDIA_SMI_QUERY}"
    output = _run(
        "nvidia-smi",
        f"--query-gpu={NVIDIA_SMI_QUERY}",
        "--format=csv,noheader,nounits",
    )
    if output is None:
        return (
            (),
            (),
            (
                f"{GPU_NOT_DETERMINED} — nvidia-smi is absent or failed. This is "
                "a machine without an NVIDIA card as far as anything here can "
                "tell; AMD and Apple GPUs are invisible to it.",
            ),
        )
    gpus: list[dict[str, Any]] = []
    facts: list[dict[str, str]] = []
    notes: list[str] = []
    for line in output.strip().splitlines():
        if not line.strip():
            continue
        gpu = _parse_gpu_row(line)
        if gpu is None:
            notes.append(
                f"{GPU_ROW_UNREAD}, so that card is missing from the scan: "
                f"{line.strip()!r}."
            )
            continue
        gpus.append(gpu)
        facts.append({"field": f"gpu[{gpu['index']}].vram.total_mib", "how": how})
        facts.append({"field": f"gpu[{gpu['index']}].vram.free_mib", "how": how})
        facts.append(
            {
                "field": f"gpu[{gpu['index']}].vram.reserved_mib",
                "how": f"{how} (total-used-free)",
            }
        )
    if not gpus and not notes:
        return (), (), ("GPU: nvidia-smi answered but reported no device.",)
    return tuple(gpus), tuple(facts), tuple(notes)


def _scan_memory() -> tuple[
    dict[str, float] | None,
    tuple[dict[str, str], ...],
    tuple[str, ...],
]:
    text = _read_meminfo()
    if text is None:
        return None, (), ("Memory: not determined — /proc/meminfo is unreadable.",)
    total = _kb_field(text, "MemTotal")
    available = _kb_field(text, "MemAvailable")
    if total is None:
        return None, (), ("Memory: /proc/meminfo carried no MemTotal.",)
    if available is None:
        available = _kb_field(text, "MemFree")
        how_available = "/proc/meminfo MemFree (no MemAvailable)"
    else:
        how_available = "/proc/meminfo MemAvailable"
    if available is None:
        return (
            None,
            (),
            ("Memory: MemTotal was readable but nothing reported free memory.",),
        )
    memory = {
        "total_gb": round(total / KB_PER_GB, 1),
        "available_gb": round(available / KB_PER_GB, 1),
    }
    facts = (
        {"field": "memory.total_gb", "how": "/proc/meminfo MemTotal"},
        {"field": "memory.available_gb", "how": how_available},
    )
    return memory, facts, ()


def _scan_cpu() -> tuple[
    dict[str, int] | None,
    tuple[dict[str, str], ...],
    tuple[str, ...],
]:
    count = os.cpu_count()
    if count is None:
        return None, (), ("CPU: not determined — os.cpu_count() returned None.",)
    cpu = {"cores": count, "threads": count}
    facts = ({"field": "cpu.threads", "how": "os.cpu_count()"},)
    notes = (
        "CPU: os.cpu_count() reports the thread count; cores are taken as the "
        "same number (no SMT claim either way).",
    )
    return cpu, facts, notes


def _scan_bandwidth() -> tuple[
    dict[str, Any] | None,
    tuple[dict[str, str], ...],
    tuple[str, ...],
]:
    measured = measure_bandwidth()
    if measured is None:
        return (
            None,
            (),
            (
                "Memory bandwidth: not measured — the copy loop produced no "
                "usable timing.",
            ),
        )
    return (
        measured,
        ({"field": "bandwidth.measured_gbps", "how": measured["how"]},),
        (),
    )


def _default_weights_dir() -> str:
    override = os.environ.get(WEIGHTS_DIR_ENV)
    if override:
        return os.path.expanduser(override)
    return os.path.expanduser("~/.cache/mcgyvr/weights")


def _scan_disk(
    weights_dir: str | None = None,
) -> tuple[dict[str, Any], tuple[dict[str, str], ...]]:
    path = weights_dir if weights_dir is not None else _default_weights_dir()
    free = _free_bytes(path)
    disk = {"path": path, "free_gb": round(free / BYTES_PER_GB, 1)}
    return disk, ({"field": "disk.free_gb", "how": f"free space on {path}"},)


def _scan_docker() -> tuple[str | None, tuple[str, ...]]:
    """The version the rig's docker daemon reports, or None with a note.

    Read with the rig's own CLI, as the user the scan runs as: a daemon that
    user cannot reach is not read, and says so.
    """
    output = _run("docker", "version", "--format", DOCKER_VERSION_FORMAT)
    version = (output or "").strip()
    if not version:
        return None, (
            "Docker: not read — no docker CLI here, or its daemon did not answer "
            "this user.",
        )
    return version, ()


def _parse_ip_addr(output: str) -> list[dict[str, str]]:
    """``ip -4 -o addr show``: ``<n>: <interface> inet <address>/<prefix> ...``."""
    found: list[dict[str, str]] = []
    for line in output.splitlines():
        parts = line.split()
        if "inet" not in parts[:3] or len(parts) < 4:
            continue
        at = parts.index("inet")
        if at + 1 >= len(parts):
            continue
        found.append(
            {
                "interface": parts[at - 1].split("@")[0],
                "address": parts[at + 1].split("/")[0],
            }
        )
    return found


def _scan_network() -> tuple[
    dict[str, Any],
    tuple[dict[str, str], ...],
    tuple[str, ...],
]:
    """Where this machine is reached, as it says itself. Nothing is resolved.

    The address the ssh session arrived at is the one the controller reached
    it by; the interface addresses are what else it holds. Which one a worker
    listens on is picked by the controller from these, never looked up.
    """
    said = os.environ.get(SSH_CONNECTION_ENV, "").split()
    reached = said[2] if len(said) == 4 else None
    output = _run("ip", *IP_ADDR_ARGS)
    ipv4 = _parse_ip_addr(output) if output is not None else []
    facts: list[dict[str, str]] = []
    notes: list[str] = []
    if reached is None:
        notes.append(
            "Network: not reached over ssh (no SSH_CONNECTION), so the address "
            "it was reached at is not known."
        )
    else:
        facts.append(
            {"field": "network.reached_at", "how": "local address in SSH_CONNECTION"}
        )
    if output is None:
        notes.append(
            "Network: `ip " + " ".join(IP_ADDR_ARGS) + "` is absent or failed, "
            "so the addresses on its interfaces are not read."
        )
    else:
        facts.append({"field": "network.ipv4", "how": "ip " + " ".join(IP_ADDR_ARGS)})
    return {"reached_at": reached, "ipv4": ipv4}, tuple(facts), tuple(notes)


def scan() -> dict[str, Any]:
    """Measure this machine and return the scan payload ``Scan.from_json`` reads."""
    machine, machine_facts, machine_notes = _scan_machine()
    gpus, gpu_facts, gpu_notes = _scan_gpus()
    memory, memory_facts, memory_notes = _scan_memory()
    cpu, cpu_facts, cpu_notes = _scan_cpu()
    bandwidth, bandwidth_facts, bandwidth_notes = _scan_bandwidth()
    disk, disk_facts = _scan_disk()
    docker, docker_notes = _scan_docker()
    network, network_facts, network_notes = _scan_network()
    return {
        "machine": machine,
        "gpus": gpus,
        "memory": memory,
        "cpu": cpu,
        "bandwidth": bandwidth,
        "disk": disk,
        "docker": docker,
        "network": network,
        "notes": [
            *machine_notes,
            *gpu_notes,
            *memory_notes,
            *cpu_notes,
            *bandwidth_notes,
            *docker_notes,
            *network_notes,
        ],
        "facts": [
            *machine_facts,
            *gpu_facts,
            *memory_facts,
            *cpu_facts,
            *bandwidth_facts,
            *disk_facts,
            *network_facts,
        ],
    }


def main() -> None:
    print(json.dumps(scan(), indent=2))


if __name__ == "__main__":
    main()
