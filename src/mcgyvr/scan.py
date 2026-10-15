"""A scan is measured on the machine it describes, and says how.

Everything else here sizes work against numbers a machine *claims*: the
capability table ships pre-measured, and :mod:`mcgyvr.detect` reads nameplates
on purpose, because a 30-second install cannot afford a benchmark. This module
is the other half of that trade, for the one question a nameplate cannot
answer — whether a rig can hold this model *right now*. So every number below
is read at the moment it is reported: free VRAM as well as total, available RAM
as well as total, and bandwidth timed rather than looked up, since a
DDR5-5600 figure describes the modules a machine was sold with and not the
machine they ended up in.

Nothing here measures anything. The one reader of a machine is
:mod:`mcgyvr.serving.rigscan`: :func:`scan` runs it here, and :func:`scan_over`
ships it to a rig as ``python3 -I -B -`` and reads its answer back, so a
laptop never infers a rig's hardware from the models a backend says it is
holding. Local and SSH differ in access only; the answer has one shape,
:class:`Scan`, parsed by :meth:`Scan.from_json`, and no access yields a
smaller answer rather than a wrong one.

Three rules shape what a scan says.

1. **Absence is an outcome, not an error** — the same rule :mod:`mcgyvr.detect`
   runs on. A missing ``nvidia-smi``, an unreadable ``/proc/meminfo`` or an
   unreachable rig makes the scan smaller and adds a note; nothing raises
   because a tool is not installed. A note matters as much as the absence: a
   silent gap reads as "no GPU" when it may mean "not determined".
2. **Volatile and stable numbers are different kinds of fact.** Used VRAM,
   available RAM and free disk are expected to move between two scans of one
   machine; total VRAM, GPU names, total RAM and core counts are not. The one
   record of a machine is its rig file (:mod:`mcgyvr.serving.rigfile`), and
   :func:`mcgyvr.serving.rigfile.moved` flags only the second kind, because an
   alarm that fires every time someone opens a browser is an alarm nobody
   reads.
3. **A scan runs where it describes.** A laptop cannot see a rig's free VRAM,
   so the remote transport reads the rig on the rig.

The seam onto a remote rig — :func:`_ssh` — is a module-level function rather
than a call inlined where it is needed, so a suite can state what a rig
answered and assert on how this code treats it without owning the rig.
"""

from __future__ import annotations

import json
import platform
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

# A remote scan measures bandwidth on the far end, so it is not instant; the
# budget is for a rig that is up and working, not for one that is gone.
SSH_TIMEOUT_S = 60.0

BYTES_PER_GB = 1024.0**3

_Facts = tuple["Fact", ...]
_Notes = tuple[str, ...]


# Named for the outcome it reports rather than with an Error suffix (N818):
# an unreachable host is a fact a sweep records and hands back in
# ``Sweep.unreachable``, not a failure of the sweep.
class Unreachable(Exception):  # noqa: N818
    """A host whose ssh transport could not be reached. Carries which one."""

    def __init__(self, host: str) -> None:
        super().__init__(f"{host}: no answer over ssh")
        self.host = host


class ScannerMissing(Exception):  # noqa: N818
    """A rig that answered ssh but could not run the shipped scan command.

    This is the modern spelling of "no mcgyvr installed": the rig is up and
    reachable, but the far end has no python3 (or the shipped command failed
    for another reason), so no measurement came back.
    """

    def __init__(self, host: str, said: str = "") -> None:
        shown = f" ({said.strip()[:300]})" if said.strip() else ""
        super().__init__(f"{host}: no scanner over ssh{shown}")
        self.host = host


class ScanFailed(Exception):  # noqa: N818
    """A rig that ran the shipped scan but printed no parseable scan."""

    def __init__(self, host: str) -> None:
        super().__init__(f"{host}: the shipped scan printed no parseable scan")
        self.host = host


@dataclass(frozen=True)
class Fact:
    """A field, and how it came to be known.

    A measured value with no provenance is indistinguishable from a guess, and
    a scan has to be explainable to the person whose machine it describes.
    """

    field: str
    how: str


@dataclass(frozen=True)
class Mismatch:
    """A stable field that disagrees with what the last scan of this machine found."""

    field: str
    prior: object
    measured: object


@dataclass(frozen=True)
class Vram:
    """One card's memory. ``free`` is the number that decides a fit today.

    ``reserved`` is the remainder the driver holds and never hands to a process.
    It is carried rather than folded into
    ``used`` because the two are answerable by different people -- used is a
    workload and reserved is the card -- and because carrying it is what lets
    the four numbers close: ``total == used + free + reserved``, always.
    """

    total_mib: int
    used_mib: int
    free_mib: int
    reserved_mib: int = 0


@dataclass(frozen=True)
class Memory:
    """System memory. ``available_gb`` is the kernel's own estimate of what a
    new workload could get without swapping — free memory alone understates it."""

    total_gb: float
    available_gb: float


@dataclass(frozen=True)
class Cpu:
    """Cores and threads kept apart, because they are different constraints.

    Twenty threads on ten cores is ten cores' worth of throughput; conflating
    them doubles the apparent machine.
    """

    cores: int
    threads: int

    @property
    def smt(self) -> bool:
        return self.threads > self.cores


@dataclass(frozen=True)
class Bandwidth:
    """Measured memory throughput, and the method that produced it.

    ``how`` is not decoration: a number from a copy loop and a number off a
    module's nameplate are not comparable, and only one of them describes the
    machine it was read on.
    """

    measured_gbps: float
    how: str


@dataclass(frozen=True)
class Disk:
    """Free space where weights would land — the path matters as much as the number."""

    path: Path
    free_gb: float
    total_gb: float | None = None
    device: str | None = None


@dataclass(frozen=True)
class ModelOnDisk:
    """One weights file on disk, named enough to be reused instead of fetched.

    ``name`` is the model id/name read off the file name; ``quant`` is the
    GGUF quantisation when the file name carries one, else None (safetensors
    shards name their model by the directory they sit in). ``size_bytes`` is
    the file's size, which is what a later download step matches before it
    spends the bandwidth.
    """

    name: str
    quant: str | None
    size_bytes: int
    path: Path


@dataclass(frozen=True)
class Interface:
    """One IPv4 address on one of the machine's network interfaces."""

    interface: str
    address: str


@dataclass(frozen=True)
class Network:
    """How the machine says it is reached, as it read it itself.

    ``reached_at`` is the address its ssh session arrived at (the local
    address in ``SSH_CONNECTION``), ``None`` when it was not reached over ssh;
    ``ipv4`` is every IPv4 address on its interfaces. Read on the far end of a
    remote scan (:mod:`mcgyvr.serving.rigscan`), so the controller resolves no
    name to learn where a rig is: :func:`mcgyvr.serving.rigfile.private_ipv4`
    picks from what the rig said.
    """

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
    """What one machine measured of itself, with provenance and gaps."""

    machine: Machine
    gpus: tuple[Gpu, ...] = ()
    memory: Memory | None = None
    cpu: Cpu | None = None
    bandwidth: Bandwidth | None = None
    disk: Disk | None = None
    models_on_disk: tuple[ModelOnDisk, ...] = ()
    notes: _Notes = ()
    facts: _Facts = ()
    #: The version the machine's own docker daemon reports, read by the one
    #: reader (:mod:`mcgyvr.serving.rigscan`) as the user it runs as. ``None``
    #: when it was not read: a daemon may not answer its user.
    docker: str | None = None
    #: How the machine says it is reached, read by the one reader where the
    #: machine is. ``None`` when a reading carried none.
    network: Network | None = None

    @property
    def gpus_determined(self) -> bool:
        """Whether :attr:`gpus` is every card the machine has, as far as
        nvidia-smi can say — read off the notes, which travel with the scan:
        the reader's own words for a card list that is not the whole answer."""
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
        """Build a scan by hand, for callers that need a machine to reason about.

        Only what is named is present, so a constructed scan can express the
        same gaps a measured one can. Every field named gets a fact saying it
        was constructed — a hand-built scan that claimed to have been measured
        would defeat the point of carrying provenance at all.
        """
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
            # One number named is a machine with no SMT claim either way, so
            # the other takes its value rather than being invented.
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
        """The same machine with its cards holding ``mib`` — a load, not a rescan."""
        gpus = tuple(
            replace(
                gpu,
                vram=Vram(
                    total_mib=gpu.vram.total_mib,
                    used_mib=mib,
                    # The reserve is the card's, so a hypothetical load does
                    # not get to spend it: only what was free plus what this
                    # machine's own workload was holding is on offer.
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
        """Read a scan back. The wire shape is the transport for a remote scan
        as well as the on-disk record, so there is only ever one parser."""
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
                        # A stored scan that carries no reserve reads as zero.
                        reserved_mib=int(gpu["vram"].get("reserved_mib", 0)),
                    ),
                )
                for gpu in raw.get("gpus") or ()
            ),
            # A total with no available figure (sysctl's, on a Mac) is no
            # memory a fit can be sized against.
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
    """How this process can get at a machine. ``None`` is here, itself."""

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
    """What a sweep of several machines found, and which ones it could not reach.

    The hosts that did not answer are carried rather than dropped: a plan made
    from two rigs when three were asked for is a different plan, and the caller
    has to be able to see which one is missing.
    """

    scans: tuple[Scan, ...] = ()
    unreachable: tuple[str, ...] = ()


def _ssh(host: str, command: str) -> str:
    """Run one read-only detection command on another machine, or say it is not there.

    Through :func:`mcgyvr.serving.gatelib.ssh_read_only`, the sanctioned
    read-only ssh path: it admits only the shipped-reader line, the ``*.gguf``
    discovery line and the shipped-reader header-read line, and refuses (exit
    2) anything else. A remote scan is a rig read, and only the door's
    read-only detection commands are admitted here; launch, sleep and wake
    still go through :func:`mcgyvr.serving.gatelib.ssh` under the door.
    ``BatchMode`` keeps a host whose key is not set up from parking the sweep
    on a password prompt: no credentials means unreachable. A rig that answers
    ssh but whose remote command fails is a different outcome, reported as
    :class:`ScannerMissing` rather than a lost ssh connection.
    """
    # Imported here and not at the top: `mcgyvr.serving` imports this module.
    from mcgyvr.serving import gatelib

    try:
        done = gatelib.ssh_read_only(host, command, timeout=SSH_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        raise Unreachable(host) from None
    if done.returncode != 0:
        raise ScannerMissing(host, done.stderr)
    return done.stdout


def default_weights_dir() -> Path:
    """The path whose free space a scan reports when the caller names none, as
    the one reader names it (:func:`mcgyvr.serving.rigscan.default_weights_dir`)."""
    from mcgyvr.serving import rigscan

    return Path(rigscan.default_weights_dir())


def scan(weights_dir: Path | None = None, model_stores: Sequence[Path] = ()) -> Scan:
    """Read this machine with the one reader. Never raises: a bare machine is a
    valid answer."""
    return Scan.from_json(json.dumps(reading(weights_dir, model_stores)))


def reading(
    weights_dir: Path | None = None, model_stores: Sequence[Path] = ()
) -> dict[str, Any]:
    """This machine's whole reading (:func:`mcgyvr.serving.rigscan.scan`): what
    :func:`scan` parses, and what a rig file keeps."""
    from mcgyvr.serving import rigscan

    return rigscan.scan(
        weights_dir=None if weights_dir is None else str(weights_dir),
        model_stores=tuple(str(store) for store in model_stores),
    )


def local_machine_id() -> str:
    """The id of *this* machine, without measuring anything.

    A caller that only needs to know which record describes the machine it is
    running on — resolving a source that says ``localhost`` to the record of
    whatever this host calls itself — is asking about identity, not about
    hardware, and pays for no measurement to find out. Identity, not the name:
    the one reader derives the id from ``/etc/machine-id`` where there is one
    (:func:`mcgyvr.serving.rigscan.machine_id`), so this stays right across a
    rename, and two machines that happen to share a hostname stay apart.
    """
    from mcgyvr.serving import rigscan

    return rigscan.machine_id()


def _remote_scan_command() -> str:
    """The read-only line that ships the one reader to the rig."""
    # Imported here and not at the top: `mcgyvr.serving` imports this module.
    from mcgyvr.serving import gatelib

    return gatelib.scan_read_command()


def read_over(reach: Reach) -> dict[str, Any]:
    """The one reader's whole document of the machine ``reach`` reaches.

    The remote branch ships the one reader to the far end as
    ``python3 -I -B -`` and reads its answer back, which is the only way the
    numbers can be measured rather than inferred. A rig that answers ssh but
    cannot run the reader raises :class:`ScannerMissing`; one that runs it but
    prints no document raises :class:`ScanFailed`.
    """
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
    """Scan the machine ``reach`` reaches, whichever side of the wire it is on.

    One reading (:func:`read_over`), parsed: the reason the two branches
    return one type.
    """
    document = read_over(reach)
    try:
        return Scan.from_json(json.dumps(document))
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ScanFailed(reach.host or "localhost") from None


def scan_all(hosts: Sequence[str] = ()) -> Sweep:
    """Scan this machine and every named host. A host that is gone is reported.

    The local machine is always in the sweep: it is the one machine access can
    never fail for, and a sweep that returned nothing because a rig was asleep
    would be less true than one that returns the laptop.
    """
    scans: list[Scan] = [scan_over(Reach.local())]
    unreachable: list[str] = []
    for host in dict.fromkeys(hosts):
        try:
            scans.append(scan_over(Reach.ssh(host)))
        except (Unreachable, ScannerMissing, ScanFailed):
            unreachable.append(host)
    return Sweep(scans=tuple(scans), unreachable=tuple(unreachable))
