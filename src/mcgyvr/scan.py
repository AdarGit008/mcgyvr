""

from __future__ import annotations

import json
import platform
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

#
#
SSH_TIMEOUT_S = 60.0

BYTES_PER_GB = 1024.0**3

_Facts = tuple["Fact", ...]
_Notes = tuple[str, ...]


#
#
#
class Unreachable(Exception):  #
    ""

    def __init__(self, host: str) -> None:
        super().__init__(f"{host}: no answer over ssh")
        self.host = host


class ScannerMissing(Exception):  #
    ""

    def __init__(self, host: str, said: str = "") -> None:
        shown = f" ({said.strip()[:300]})" if said.strip() else ""
        super().__init__(f"{host}: no scanner over ssh{shown}")
        self.host = host


class ScanFailed(Exception):  #
    ""

    def __init__(self, host: str) -> None:
        super().__init__(f"{host}: the shipped scan printed no parseable scan")
        self.host = host


@dataclass(frozen=True)
class Fact:
    ""

    field: str
    how: str


@dataclass(frozen=True)
class Mismatch:
    ""

    field: str
    prior: object
    measured: object


@dataclass(frozen=True)
class Vram:
    ""

    total_mib: int
    used_mib: int
    free_mib: int
    reserved_mib: int = 0


@dataclass(frozen=True)
class Memory:
    ""

    total_gb: float
    available_gb: float


@dataclass(frozen=True)
class Cpu:
    ""

    cores: int
    threads: int

    @property
    def smt(self) -> bool:
        return self.threads > self.cores


@dataclass(frozen=True)
class Bandwidth:
    ""

    measured_gbps: float
    how: str


@dataclass(frozen=True)
class Disk:
    ""

    path: Path
    free_gb: float
    total_gb: float | None = None
    device: str | None = None


@dataclass(frozen=True)
class ModelOnDisk:
    ""

    name: str
    quant: str | None
    size_bytes: int
    path: Path


@dataclass(frozen=True)
class Interface:
    ""

    interface: str
    address: str


@dataclass(frozen=True)
class Network:
    ""

    reached_at: str | None
    ipv4: tuple[Interface, ...] = ()


@dataclass(frozen=True)
class Gpu:
    index: int
    name: str
    vram: Vram


@dataclass(frozen=True)
class Machine:
    id: str
    host: str
    kernel: str


@dataclass(frozen=True)
class Scan:
    ""

    machine: Machine
    gpus: tuple[Gpu, ...] = ()
    memory: Memory | None = None
    cpu: Cpu | None = None
    bandwidth: Bandwidth | None = None
    disk: Disk | None = None
    models_on_disk: tuple[ModelOnDisk, ...] = ()
    notes: _Notes = ()
    facts: _Facts = ()
    #
    #
    #
    docker: str | None = None
    #
    #
    network: Network | None = None

    @property
    def gpus_determined(self) -> bool:
        ""
        from mcgyvr.serving.rigscan import GPU_NOT_DETERMINED, GPU_ROW_UNREAD

        return not any(
            note.startswith((GPU_NOT_DETERMINED, GPU_ROW_UNREAD)) for note in self.notes
        )

    @classmethod
    def of(
        cls,
        *,
        host: str = "localhost",
        vram_mib: int | None = None,
        ram_gb: float | None = None,
        disk_free_gb: float | None = None,
        cores: int | None = None,
        threads: int | None = None,
        bandwidth_gbps: float | None = None,
    ) -> Scan:
        ""
        facts: list[Fact] = []
        gpus: tuple[Gpu, ...] = ()
        if vram_mib is not None:
            gpus = (
                Gpu(
                    index=0,
                    name="gpu-0",
                    vram=Vram(total_mib=vram_mib, used_mib=0, free_mib=vram_mib),
                ),
            )
            facts.append(Fact(field="gpu[0].vram.total_mib", how="Scan.of"))
        memory = None
        if ram_gb is not None:
            memory = Memory(total_gb=ram_gb, available_gb=ram_gb)
            facts.append(Fact(field="memory.total_gb", how="Scan.of"))
        cpu = None
        if cores is not None or threads is not None:
            #
            #
            cpu = Cpu(cores=cores or threads or 0, threads=threads or cores or 0)
            facts.append(Fact(field="cpu.cores", how="Scan.of"))
        bandwidth = None
        if bandwidth_gbps is not None:
            bandwidth = Bandwidth(measured_gbps=bandwidth_gbps, how="Scan.of")
            facts.append(Fact(field="bandwidth.measured_gbps", how="Scan.of"))
        disk = None
        if disk_free_gb is not None:
            disk = Disk(path=default_weights_dir(), free_gb=disk_free_gb)
            facts.append(Fact(field="disk.free_gb", how="Scan.of"))
        return cls(
            machine=Machine(id=f"id-{host}", host=host, kernel=platform.release()),
            gpus=gpus,
            memory=memory,
            cpu=cpu,
            bandwidth=bandwidth,
            disk=disk,
            facts=tuple(facts),
        )

    def with_vram_used(self, mib: int) -> Scan:
        ""
        gpus = tuple(
            replace(
                gpu,
                vram=Vram(
                    total_mib=gpu.vram.total_mib,
                    used_mib=mib,
                    #
                    #
                    #
                    free_mib=max(gpu.vram.total_mib - gpu.vram.reserved_mib - mib, 0),
                    reserved_mib=gpu.vram.reserved_mib,
                ),
            )
            for gpu in self.gpus
        )
        return replace(self, gpus=gpus)

    def to_json(self) -> str:
        payload: dict[str, Any] = {
            "machine": {
                "id": self.machine.id,
                "host": self.machine.host,
                "kernel": self.machine.kernel,
            },
            "gpus": [
                {
                    "index": gpu.index,
                    "name": gpu.name,
                    "vram": {
                        "total_mib": gpu.vram.total_mib,
                        "used_mib": gpu.vram.used_mib,
                        "free_mib": gpu.vram.free_mib,
                        "reserved_mib": gpu.vram.reserved_mib,
                    },
                }
                for gpu in self.gpus
            ],
            "memory": (
                None
                if self.memory is None
                else {
                    "total_gb": self.memory.total_gb,
                    "available_gb": self.memory.available_gb,
                }
            ),
            "cpu": (
                None
                if self.cpu is None
                else {"cores": self.cpu.cores, "threads": self.cpu.threads}
            ),
            "bandwidth": (
                None
                if self.bandwidth is None
                else {
                    "measured_gbps": self.bandwidth.measured_gbps,
                    "how": self.bandwidth.how,
                }
            ),
            "disk": (
                None
                if self.disk is None
                else {
                    "path": str(self.disk.path),
                    "free_gb": self.disk.free_gb,
                    "total_gb": self.disk.total_gb,
                    "device": self.disk.device,
                }
            ),
            "models_on_disk": [
                {
                    "name": model.name,
                    "quant": model.quant,
                    "size_bytes": model.size_bytes,
                    "path": str(model.path),
                }
                for model in self.models_on_disk
            ],
            "docker": self.docker,
            "network": (
                None
                if self.network is None
                else {
                    "reached_at": self.network.reached_at,
                    "ipv4": [
                        {"interface": one.interface, "address": one.address}
                        for one in self.network.ipv4
                    ],
                }
            ),
            "notes": list(self.notes),
            "facts": [{"field": f.field, "how": f.how} for f in self.facts],
        }
        return json.dumps(payload, indent=2) + "\n"

    @classmethod
    def from_json(cls, text: str) -> Scan:
        ""
        raw: Any = json.loads(text)
        machine = raw.get("machine") or {}
        memory = raw.get("memory")
        cpu = raw.get("cpu")
        bandwidth = raw.get("bandwidth")
        disk = raw.get("disk")
        network = raw.get("network")
        return cls(
            machine=Machine(
                id=str(machine.get("id", "")),
                host=str(machine.get("host", "")),
                kernel=str(machine.get("kernel", "")),
            ),
            gpus=tuple(
                Gpu(
                    index=int(gpu["index"]),
                    name=str(gpu["name"]),
                    vram=Vram(
                        total_mib=int(gpu["vram"]["total_mib"]),
                        used_mib=int(gpu["vram"]["used_mib"]),
                        free_mib=int(gpu["vram"]["free_mib"]),
                        #
                        reserved_mib=int(gpu["vram"].get("reserved_mib", 0)),
                    ),
                )
                for gpu in raw.get("gpus") or ()
            ),
            #
            #
            memory=(
                None
                if memory is None or memory.get("available_gb") is None
                else Memory(
                    total_gb=float(memory["total_gb"]),
                    available_gb=float(memory["available_gb"]),
                )
            ),
            cpu=(
                None
                if cpu is None
                else Cpu(cores=int(cpu["cores"]), threads=int(cpu["threads"]))
            ),
            bandwidth=(
                None
                if bandwidth is None
                else Bandwidth(
                    measured_gbps=float(bandwidth["measured_gbps"]),
                    how=str(bandwidth["how"]),
                )
            ),
            disk=(
                None
                if disk is None
                else Disk(
                    path=Path(str(disk["path"])),
                    free_gb=float(disk["free_gb"]),
                    total_gb=(
                        None
                        if disk.get("total_gb") is None
                        else float(disk["total_gb"])
                    ),
                    device=(
                        None if disk.get("device") is None else str(disk["device"])
                    ),
                )
            ),
            models_on_disk=tuple(
                ModelOnDisk(
                    name=str(model["name"]),
                    quant=None if model.get("quant") is None else str(model["quant"]),
                    size_bytes=int(model["size_bytes"]),
                    path=Path(str(model["path"])),
                )
                for model in raw.get("models_on_disk") or ()
            ),
            notes=tuple(str(note) for note in raw.get("notes") or ()),
            facts=tuple(
                Fact(field=str(fact["field"]), how=str(fact["how"]))
                for fact in raw.get("facts") or ()
            ),
            docker=str(raw["docker"]) if raw.get("docker") else None,
            network=(
                None
                if network is None
                else Network(
                    reached_at=(
                        None
                        if network.get("reached_at") is None
                        else str(network["reached_at"])
                    ),
                    ipv4=tuple(
                        Interface(
                            interface=str(one["interface"]),
                            address=str(one["address"]),
                        )
                        for one in network.get("ipv4") or ()
                    ),
                )
            ),
        )


@dataclass(frozen=True)
class Reach:
    ""

    host: str | None = None

    @classmethod
    def local(cls) -> Reach:
        return cls(host=None)

    @classmethod
    def ssh(cls, host: str) -> Reach:
        return cls(host=host)

    @property
    def is_local(self) -> bool:
        return self.host is None


@dataclass(frozen=True)
class Sweep:
    ""

    scans: tuple[Scan, ...] = ()
    unreachable: tuple[str, ...] = ()


def _ssh(host: str, command: str) -> str:
    ""
    #
    from mcgyvr.serving import gatelib

    try:
        done = gatelib.ssh_read_only(host, command, timeout=SSH_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        raise Unreachable(host) from None
    if done.returncode != 0:
        raise ScannerMissing(host, done.stderr)
    return done.stdout


def default_weights_dir() -> Path:
    ""
    from mcgyvr.serving import rigscan

    return Path(rigscan.default_weights_dir())


def scan(weights_dir: Path | None = None, model_stores: Sequence[Path] = ()) -> Scan:
    ""
    return Scan.from_json(json.dumps(reading(weights_dir, model_stores)))


def reading(
    weights_dir: Path | None = None, model_stores: Sequence[Path] = ()
) -> dict[str, Any]:
    ""
    from mcgyvr.serving import rigscan

    return rigscan.scan(
        weights_dir=None if weights_dir is None else str(weights_dir),
        model_stores=tuple(str(store) for store in model_stores),
    )


def local_machine_id() -> str:
    ""
    from mcgyvr.serving import rigscan

    return rigscan.machine_id()


def _remote_scan_command() -> str:
    ""
    #
    from mcgyvr.serving import gatelib

    return gatelib.scan_read_command()


def read_over(reach: Reach) -> dict[str, Any]:
    ""
    if reach.host is None:
        return reading()
    text = _ssh(reach.host, _remote_scan_command())
    try:
        document = json.loads(text)
    except ValueError:
        raise ScanFailed(reach.host) from None
    if not isinstance(document, dict):
        raise ScanFailed(reach.host)
    return document


def scan_over(reach: Reach) -> Scan:
    ""
    document = read_over(reach)
    try:
        return Scan.from_json(json.dumps(document))
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ScanFailed(reach.host or "localhost") from None


def scan_all(hosts: Sequence[str] = ()) -> Sweep:
    ""
    scans: list[Scan] = [scan_over(Reach.local())]
    unreachable: list[str] = []
    for host in dict.fromkeys(hosts):
        try:
            scans.append(scan_over(Reach.ssh(host)))
        except (Unreachable, ScannerMissing, ScanFailed):
            unreachable.append(host)
    return Sweep(scans=tuple(scans), unreachable=tuple(unreachable))
