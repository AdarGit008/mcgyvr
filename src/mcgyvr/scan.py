"""A machine as it was measured, and the two ways to measure it.

The dataclasses here are the shape one scan fills in: the machine, its cards and
the VRAM each has left, its RAM, CPU, measured memory bandwidth, free disk, the
model files on disk, docker, and its addresses. A number that was not read is
absent rather than defaulted: what was absent is said in ``notes`` and how each
number was obtained is said in ``facts``.

A scan travels as json (``to_json``, ``from_json``) and is produced either here
(``reading``, ``scan``) or on the host itself over ssh (``read_over``,
``scan_over``), because free VRAM and memory bandwidth are only visible from the
machine they describe.
"""

from __future__ import annotations

import json
import platform
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# How long one ssh read may run before its host counts as unreachable.
# Each host gets this to itself; the bound is not shared across a sweep.
SSH_TIMEOUT_S = 60.0
#: The status ssh itself exits with when it fails (no connection, no login).
SSH_FAILED = 255

BYTES_PER_GB = 1024.0**3

#: Interface names starting with these are container and VM bridges and their
#: pairs: docker's own bridges, a compose network's br-*, each container's veth*
#: and libvirt's virbr*.
BRIDGE_PREFIXES = ("docker", "br-", "veth", "virbr")

_Facts = tuple["Fact", ...]
_Notes = tuple[str, ...]


# The three ways a remote read fails to produce a scan, told apart so that a
# caller can say which one happened: the host did not answer, it answered
# without the shipped reader, or the reader printed what no Scan can be read
# from.
class Unreachable(Exception):  # noqa: N818
    """The host gave no answer over ssh, so nothing about it was read.

    Raised for a transport failure or a timeout of the ssh call: the repair is
    access to that host, not anything on the host.
    """

    def __init__(self, host: str) -> None:
        super().__init__(f"{host}: no answer over ssh")
        self.host = host


class ScannerMissing(Exception):  # noqa: N818
    """The host answered, but the read command it was given failed there.

    This is what a host without the shipped reader looks like from here: ssh
    exits non-zero and the message carries up to 300 characters of its stderr,
    which is where the reason is usually said.
    """

    def __init__(self, host: str, said: str = "", code: int | None = None) -> None:
        shown = f" ({said.strip()[:300]})" if said.strip() else ""
        super().__init__(f"{host}: no scanner over ssh{shown}")
        self.host = host
        #: The exit status, when known: 255 is ssh's own failure, not the rig's.
        self.code = code


class ScanFailed(Exception):  # noqa: N818
    """The host answered and exited clean, but what it printed is not a scan.

    Raised when the output is not json, not a json object, or a document whose
    fields cannot be read into a :class:`Scan`.
    """

    def __init__(self, host: str) -> None:
        super().__init__(f"{host}: the shipped scan printed no parseable scan")
        self.host = host


@dataclass(frozen=True)
class Fact:
    """One number in a scan and the means by which it was obtained.

    ``field`` names the reading (``gpu[0].vram.total_mib``, ``cpu.cores``) and
    ``how`` names the source that gave it (``lscpu CPU(s)``, ``Scan.of``), so a
    number can always be traced back to what produced it.
    """

    field: str
    how: str


@dataclass(frozen=True)
class Vram:
    """One card's video memory, in MiB, as the driver reported it.

    ``total_mib`` is the card's whole memory, ``used_mib`` what is allocated
    now, ``free_mib`` what the tool says is left, and ``reserved_mib`` the part
    that is neither used nor free (total - used - free, and 0 when the tool did
    not say).
    """

    total_mib: int
    used_mib: int
    free_mib: int
    reserved_mib: int = 0


@dataclass(frozen=True)
class Memory:
    """This machine's RAM, in GB of ``BYTES_PER_GB`` (1024**3) bytes.

    ``total_gb`` is the installed memory and ``available_gb`` what a new process
    could still allocate, None when the reading gave only a total (a Mac whose
    vm_stat did not answer): the total still stands, and nothing is promised
    free.
    """

    total_gb: float
    available_gb: float | None


@dataclass(frozen=True)
class Cpu:
    """The core and hardware-thread counts this machine reports.

    ``cores`` is physical cores (lscpu's Core(s) per socket x Socket(s), or
    os.cpu_count() when lscpu is silent, which counts threads) and ``threads``
    the logical CPUs.
    """

    cores: int
    threads: int
    #: The CPU's name as the machine prints it, None when it was not read.
    model: str | None = None
    #: The performance cores of a CPU that has two kinds (macOS
    #: hw.perflevel0.physicalcpu), None elsewhere.
    performance_cores: int | None = None


@dataclass(frozen=True)
class Bandwidth:
    """A memory bandwidth figure measured on this machine, in GB/s.

    ``how`` names the measurement that produced it, so a number from the copy
    loop is never mistaken for one read off a module nameplate.
    """

    measured_gbps: float
    how: str


@dataclass(frozen=True)
class Disk:
    """Free space on the filesystem that holds a weights directory.

    ``path`` is the directory that was probed and ``free_gb`` what it had left;
    ``total_gb`` and ``device`` are None when they could not be read (no usable
    filesystem, or no entry for it in /proc/self/mounts).
    """

    path: Path
    free_gb: float
    total_gb: float | None = None
    device: str | None = None


@dataclass(frozen=True)
class ModelOnDisk:
    """One model file found on this machine's disk.

    ``name`` is the file's name with ``.gguf`` and any quantization suffix
    removed, ``quant`` that suffix when the name carried one, ``size_bytes`` the
    file's size, and ``path`` where it is.
    """

    name: str
    quant: str | None
    size_bytes: int
    path: Path


@dataclass(frozen=True)
class Interface:
    """One IPv4 address on one network interface, as ``ip`` printed it.

    ``interface`` is the interface name without its ``@peer`` suffix and
    ``address`` the address without its prefix length.
    """

    interface: str
    address: str


@dataclass(frozen=True)
class Network:
    """Where this machine sits on the network, as the machine itself reports it.

    ``reached_at`` is the local address its ssh session arrived from
    (``SSH_CONNECTION``), None when the machine was not read over ssh; ``ipv4``
    holds one entry per address on its interfaces.
    """

    reached_at: str | None
    ipv4: tuple[Interface, ...] = ()


@dataclass(frozen=True)
class Gpu:
    """One card the scan sized.

    ``kind`` is ``gpu`` for a card with its own memory and ``unified`` for a GPU
    that shares the machine's memory (a Mac's), whose ``vram`` is the share the
    GPU may take. ``backend`` is the llama.cpp build it runs under (``cuda``,
    ``metal``, ``vulkan``, ``rocm``), and ``figure`` says whether ``vram`` is
    the card's own ``reading`` or an ``estimate``. A reading from before these
    fields reads as a CUDA card's reading.
    """

    index: int
    name: str
    vram: Vram
    kind: str = "gpu"
    backend: str = "cuda"
    figure: str = "reading"


@dataclass(frozen=True)
class Host:
    """The system a reading was taken on: ``os`` (linux, darwin, windows), ``arch``
    (x86_64, arm64; None when the reader names none) and ``version`` (the kernel
    release on Linux, the product version on macOS, the system version on
    Windows; None when unread)."""

    os: str
    arch: str | None = None
    version: str | None = None

    @classmethod
    def from_reading(cls, raw: Any) -> Host | None:
        """The host section of a reading, or None when its system is not one the
        reader reads. An arch outside the reader's names, and a version that is
        not printable or longer than its limit, read as None."""
        from mcgyvr import hubwire
        from mcgyvr.serving import rigscan

        if not isinstance(raw, dict) or raw.get("os") not in hubwire.HOST_OS:
            return None
        arch, version = raw.get("arch"), raw.get("version")
        arches = {*rigscan.ARCHES.values(), *rigscan.WINDOWS_ARCHES.values()}
        usable = (
            isinstance(version, str)
            and 0 < len(version) <= hubwire.HOST_VERSION_MAX
            and version.isprintable()
        )
        return cls(
            os=str(raw["os"]),
            arch=arch if arch in arches else None,
            version=version if usable else None,
        )


@dataclass(frozen=True)
class Machine:
    id: str
    host: str
    kernel: str


@dataclass(frozen=True)
class Scan:
    """One machine as a single reading: what it has and what could not be read.

    Every field was read from the machine, or stated by ``Scan.of``, which
    records in ``facts`` the numbers it filled; a section left None was not
    determined, never assumed, and ``notes`` carries the sentence saying why.
    ``docker`` is the version string the docker CLI printed and ``network`` the
    addresses the machine reported, both None when that part of the reading is
    absent.
    """

    machine: Machine
    gpus: tuple[Gpu, ...] = ()
    memory: Memory | None = None
    cpu: Cpu | None = None
    bandwidth: Bandwidth | None = None
    disk: Disk | None = None
    models_on_disk: tuple[ModelOnDisk, ...] = ()
    notes: _Notes = ()
    facts: _Facts = ()
    #: The docker CLI's version string, None when there is no docker here or
    #: its daemon gave no answer; ``notes`` says which of those it was.
    docker: str | None = None
    #: The address this machine was reached at, and the addresses its
    #: interfaces hold; None when the reading carried no network section.
    network: Network | None = None
    #: mcgyvr's home as this machine resolved it (``$MCGYVR_HOME``, else
    #: ``~/.mcgyvr``); None when the reading carried none, as a reading from an
    #: older scanner does.
    home: Path | None = None
    #: The system the reading was taken on; None for a reading from an older
    #: scanner.
    host: Host | None = None

    @property
    def gpus_determined(self) -> bool:
        """True unless a note says the card list is incomplete.

        A reader that was absent, or a row it printed but could not read,
        leaves ``gpus`` possibly short of the cards actually present, which
        downstream must not read as cards that were pulled.
        """
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
        """A scan stated by the caller instead of measured on a machine.

        Only the sections named are filled: ``vram_mib`` makes one card at
        index 0, ``ram_gb`` fills total and available alike, ``cores`` and
        ``threads`` stand in for each other when only one is given, and
        ``disk_free_gb`` is reported for ``default_weights_dir()``. Each number
        filled is recorded in ``facts`` as having come from ``Scan.of``, so a
        stated scan is never mistaken for a measured one.
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
            # One count is enough from the caller: cores alone give the same
            # number of threads, and threads alone the same number of cores.
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
                    "kind": gpu.kind,
                    "backend": gpu.backend,
                    "figure": gpu.figure,
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
                else {
                    "cores": self.cpu.cores,
                    "threads": self.cpu.threads,
                    "model": self.cpu.model,
                    "performance_cores": self.cpu.performance_cores,
                }
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
            "home": None if self.home is None else str(self.home),
            "host": (
                None
                if self.host is None
                else {
                    "os": self.host.os,
                    "arch": self.host.arch,
                    "version": self.host.version,
                }
            ),
            "notes": list(self.notes),
            "facts": [{"field": f.field, "how": f.how} for f in self.facts],
        }
        return json.dumps(payload, indent=2) + "\n"

    @classmethod
    def from_json(cls, text: str) -> Scan:
        """A scan read back from the json ``to_json`` writes.

        Sections that are absent or null come back as None or as empty tuples
        rather than as errors, which is how a reading from an older or a
        partial scanner still parses, and a memory section with no total is
        dropped whole while one with no available memory keeps its total.
        Whatever json and the field conversions raise
        is left to the caller, and ``scan_over`` turns that into ``ScanFailed``.
        """
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
                        # reserved_mib arrived after the first scans did: a
                        # reading that omits it has nothing to report.
                        reserved_mib=int(gpu["vram"].get("reserved_mib", 0)),
                    ),
                    # kind, backend and figure arrived with the Mac and
                    # Windows readers: a reading that omits them is of a CUDA card.
                    kind=str(gpu.get("kind") or "gpu"),
                    backend=str(gpu.get("backend") or "cuda"),
                    figure=str(gpu.get("figure") or "reading"),
                )
                for gpu in raw.get("gpus") or ()
            ),
            # A memory section with no total says nothing; one with a total and
            # no available memory keeps the total and promises nothing free.
            memory=(
                None
                if memory is None or memory.get("total_gb") is None
                else Memory(
                    total_gb=float(memory["total_gb"]),
                    available_gb=(
                        None
                        if memory.get("available_gb") is None
                        else float(memory["available_gb"])
                    ),
                )
            ),
            cpu=(
                None
                if cpu is None
                else Cpu(
                    cores=int(cpu["cores"]),
                    threads=int(cpu["threads"]),
                    model=None if cpu.get("model") is None else str(cpu["model"]),
                    performance_cores=(
                        None
                        if cpu.get("performance_cores") is None
                        else int(cpu["performance_cores"])
                    ),
                )
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
            home=Path(str(raw["home"])) if raw.get("home") else None,
            host=Host.from_reading(raw.get("host")),
        )


@dataclass(frozen=True)
class Reach:
    """Which machine a scan is for.

    ``host=None`` is this machine; anything else is that host, read over ssh.
    The two differ only in transport: the same scan runs on either.
    """

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


def _ssh(host: str, command: str, input: str | None = None) -> str:
    """Run one read command on ``host`` over ssh and return its stdout.

    The command (with its stdin, `input`) has to be one
    ``gatelib.ssh_read_only`` admits, so this channel can only read. A
    transport failure or a timeout raises ``Unreachable``, a non-zero exit
    raises ``ScannerMissing`` carrying the host's stderr, and anything else
    hands the stdout back for the caller to parse.
    """
    # The gate library refuses any command that is not the shipped reader.
    from mcgyvr.serving import gatelib

    try:
        # A POSIX read carries no stdin, and is asked exactly as it always was.
        done = (
            gatelib.ssh_read_only(host, command, timeout=SSH_TIMEOUT_S)
            if input is None
            else gatelib.ssh_read_only(
                host, command, timeout=SSH_TIMEOUT_S, input=input
            )
        )
    except (OSError, subprocess.SubprocessError):
        raise Unreachable(host) from None
    if done.returncode != 0:
        raise ScannerMissing(host, done.stderr, done.returncode)
    return done.stdout


def default_weights_dir() -> Path:
    """Where this machine keeps its weights.

    ``MCGYVR_WEIGHTS`` when set, else ``weights`` in the system's cache folder
    (``~/.cache/mcgyvr/weights`` on Linux), expanded;
    rigscan resolves it, so a local and a remote path follow the same rule.
    """
    from mcgyvr.serving import rigscan

    return Path(rigscan.default_weights_dir())


def scan(weights_dir: Path | None = None, model_stores: Sequence[Path] = ()) -> Scan:
    """Measure this machine and return it as a ``Scan``.

    The reading is rigscan's dict, read back through ``Scan.from_json``, so a
    local scan is parsed by the same code as a remote one.
    """
    return Scan.from_json(json.dumps(reading(weights_dir, model_stores)))


def reading(
    weights_dir: Path | None = None, model_stores: Sequence[Path] = ()
) -> dict[str, Any]:
    """This machine's raw reading, as the document a rig file keeps whole.

    ``weights_dir`` is where models are looked for and probed for free disk;
    rigscan defaults it to ``default_weights_dir()`` when None. ``model_stores``
    are searched for model files in addition to that directory.
    """
    from mcgyvr.serving import rigscan

    return rigscan.scan(
        weights_dir=None if weights_dir is None else str(weights_dir),
        model_stores=tuple(str(store) for store in model_stores),
    )


def local_machine_id() -> str:
    """This machine's id, as rigscan derives it, without reading anything else."""
    from mcgyvr.serving import rigscan

    return rigscan.machine_id()


def _remote_scan_command() -> str:
    """The command a remote host is asked to run.

    It is the shipped reader itself, base64'd from this installation and piped
    into python3 on the host, so a rig needs no mcgyvr installed there.
    """
    # Nothing has to exist on the host: the reader travels inside the command.
    from mcgyvr.serving import gatelib

    return gatelib.scan_read_command()


#: The rigs this process has found to be Windows on first contact, before a
#: rig file records it.
_WINDOWS_FOUND: set[str] = set()


def shipping_os(host: str) -> str:
    """How a read is shipped to ``host``: ``windows`` for a rig its rig file
    records as Windows or this process found to be one, the POSIX line
    (``linux``) for every other."""
    from mcgyvr.serving import gatelib

    if host in _WINDOWS_FOUND or gatelib.shipping_os(host) == gatelib.WINDOWS:
        return gatelib.WINDOWS
    return gatelib.LINUX


def _answers_powershell(host: str) -> bool:
    """Whether ``host``'s shell runs Windows PowerShell (the first contact's
    second question, asked when the POSIX reader did not run)."""
    from mcgyvr.serving import gatelib

    try:
        return _ssh(host, gatelib.PROBE_WINDOWS).strip() == gatelib.WINDOWS_PLATFORM
    except (Unreachable, ScannerMissing):
        return False


def _read_text(host: str) -> str:
    """What the shipped reader on ``host`` printed, shipped the way its shell
    takes it.

    A rig with no rig file is sent the POSIX line first, as every rig was; one
    that cannot run it and answers PowerShell is a Windows rig, sent the
    Windows shipment (and remembered for this process: ``mcgyvr scan --rig``
    files the reading, whose ``host.os`` says so from then on).
    """
    from mcgyvr.serving import gatelib

    if shipping_os(host) == gatelib.WINDOWS:
        sent = gatelib.scan_read(gatelib.WINDOWS)
        return _ssh(host, sent.command, sent.stdin)
    try:
        return _ssh(host, _remote_scan_command())
    except ScannerMissing as failed:
        # 255 is ssh failing to reach or log in, which no shell answered.
        if (
            failed.code == SSH_FAILED
            or gatelib.recorded_os(host) is not None
            or not _answers_powershell(host)
        ):
            raise
    _WINDOWS_FOUND.add(host)
    sent = gatelib.scan_read(gatelib.WINDOWS)
    return _ssh(host, sent.command, sent.stdin)


def read_over(reach: Reach) -> dict[str, Any]:
    """Read one machine's raw reading over ``reach``.

    A local reach calls rigscan here and opens no connection; a host reach runs
    the shipped reader there (:func:`_read_text`) and parses what it printed.
    The ssh itself raises ``Unreachable`` or ``ScannerMissing``, and output
    that is not json or not a json object raises ``ScanFailed``.
    """
    if reach.host is None:
        return reading()
    text = _read_text(reach.host)
    try:
        document = json.loads(text)
    except ValueError:
        raise ScanFailed(reach.host) from None
    if not isinstance(document, dict):
        raise ScanFailed(reach.host)
    return document


def scan_over(reach: Reach) -> Scan:
    """Read one machine over ``reach`` and return it as a ``Scan``.

    Anything the document fails to parse as — bad json, a field missing, a
    value of the wrong type — raises ``ScanFailed`` naming the host, since no
    partial scan is better than none.
    """
    document = read_over(reach)
    try:
        return Scan.from_json(json.dumps(document))
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ScanFailed(reach.host or "localhost") from None
