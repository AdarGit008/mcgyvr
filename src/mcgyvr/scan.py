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

Three rules follow from that, and they shape everything here.

1. **Absence is an outcome, not an error** — the same rule :mod:`mcgyvr.detect`
   runs on. A missing ``nvidia-smi``, an unreadable ``/proc/meminfo`` or an
   unreachable rig makes the scan smaller and adds a note; nothing raises
   because a tool is not installed. A note matters as much as the absence: a
   silent gap reads as "no GPU" when it may mean "not determined".
2. **Volatile and stable numbers are different kinds of fact.** Used VRAM,
   available RAM and free disk are expected to move between two scans of one
   machine; total VRAM, GPU names, total RAM and core counts are not.
   :func:`compare` flags only the second kind, because an alarm that fires
   every time someone opens a browser is an alarm nobody reads.
3. **A scan runs where it describes.** A laptop cannot see a rig's free VRAM,
   so the remote transport ships this same code to the far end
   (``mcgyvr scan --json``) and parses what comes back, instead of inferring
   hardware from the models a backend says it is holding. Local and SSH differ
   in access only; the answer has one shape, and no access yields a smaller
   answer rather than a wrong one.

The seams onto the outside world — :func:`_run`, :func:`_read_meminfo`,
:func:`_free_bytes`, :func:`measure_bandwidth`, :func:`_ssh` — are module-level
functions rather than calls inlined where they are needed, so a suite can state
what the hardware answered and assert on how this code treats it without owning
the hardware.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from mcgyvr.detect import COMMAND_TIMEOUT_S, MIB_PER_GB

# A remote scan measures bandwidth on the far end, so it is not instant; the
# budget is for a rig that is up and working, not for one that is gone.
SSH_TIMEOUT_S = 60.0
CONNECT_TIMEOUT_S = 5.0

# What a remote host is asked to run. It is this module, over there: the whole
# point is that the far end measures itself.
REMOTE_COMMAND = "mcgyvr scan --json"

NVIDIA_SMI_QUERY = "index,name,memory.total,memory.used"
KB_PER_GB = 1024.0 * 1024.0
BYTES_PER_GB = 1024.0**3

# Bandwidth is a measurement, so two scans of one machine never agree exactly:
# a copy loop lands within a few percent of itself run to run. Flag a change
# only when it is bigger than that band — a card moved to a slower slot, a DIMM
# dropping to single channel — and stay quiet about the noise.
# Set from the measurement's own noise, not from taste. At COPY_MIB the copy
# repeats to within 9% of itself across runs on a shared VPS, so a band a
# little wider than that is the tightest one that does not cry wolf. It still
# catches what this is for: memory that lost a channel roughly halves.
BANDWIDTH_TOLERANCE = 0.15

# Big enough to miss in any cache a desktop has AND to swamp the scheduler
# noise on a busy machine. Measured: at 64 MiB the same box reported 11.8 to
# 17.0 GB/s run to run (44% spread, which no tolerance can use); at 256 MiB
# the spread falls to 9%. The buffer is the instrument, so it is sized by what
# it takes to make the reading repeat, not by what looks modest.
COPY_MIB = 256
COPY_PASSES = 5

# Two buffers at COPY_MIB is half a gigabyte. A rig serving an MoE model with
# a few gigabytes to spare should not be pushed into swap to answer a question
# about its memory, so a tight machine is measured with the smaller buffer and
# the reading says so rather than pretending to the same precision.
COPY_MIB_TIGHT = 64
TIGHT_RAM_GB = 2.0

SCAN_ROOT_ENV = "MCGYVR_SCANS"
WEIGHTS_DIR_ENV = "MCGYVR_WEIGHTS"

# systemd's own advice is not to hand /etc/machine-id out as-is; hashing keeps
# the property this needs (same machine, same answer) without publishing an id
# other software treats as a secret.
MACHINE_ID_FILES = (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id"))

_Facts = tuple["Fact", ...]
_Notes = tuple[str, ...]


# Named for the outcome it reports rather than with an Error suffix (N818):
# an unreachable host is a fact a sweep records and hands back in
# ``Sweep.unreachable``, not a failure of the sweep.
class Unreachable(Exception):  # noqa: N818
    """A host that could not be scanned. Carries which one, for the report."""

    def __init__(self, host: str) -> None:
        super().__init__(f"{host}: no answer over ssh")
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
    """One card's memory. ``free`` is the number that decides a fit today."""

    total_mib: int
    used_mib: int
    free_mib: int


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
    notes: _Notes = ()
    facts: _Facts = ()

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
                    free_mib=max(gpu.vram.total_mib - mib, 0),
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
                else {"path": str(self.disk.path), "free_gb": self.disk.free_gb}
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
                    ),
                )
                for gpu in raw.get("gpus") or ()
            ),
            memory=(
                None
                if memory is None
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
                else Disk(path=Path(str(disk["path"])), free_gb=float(disk["free_gb"]))
            ),
            notes=tuple(str(note) for note in raw.get("notes") or ()),
            facts=tuple(
                Fact(field=str(fact["field"]), how=str(fact["how"]))
                for fact in raw.get("facts") or ()
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


def _run(binary: str, *args: str, timeout: float = COMMAND_TIMEOUT_S) -> str | None:
    """Run a tool, returning its stdout or None if it cannot be run.

    Missing, failed and unusable collapse into one answer on purpose: the
    caller's next move is the same for all three, and it is never to raise.
    """
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
    """The kernel's memory report, or None where there is no /proc."""
    try:
        return Path("/proc/meminfo").read_text(encoding="utf-8")
    except OSError:
        return None


def _free_bytes(path: Path) -> int:
    """Free bytes on the filesystem holding ``path``.

    Walks up to the nearest existing ancestor, because a weights directory is
    routinely named before it is created and the answer for the parent is the
    answer for the child once it exists.
    """
    probe = path
    while True:
        try:
            return shutil.disk_usage(probe).free
        except OSError:
            parent = probe.parent
            if parent == probe:
                return 0
            probe = parent


def _spare_gb() -> float:
    """Available RAM in GB, or 0.0 when it cannot be read.

    Only ``measure_bandwidth`` asks, and only to decide how large a buffer it
    may take. Unreadable answers 0.0 so the smaller buffer is chosen: a scan
    that cannot tell how much room it has should not help itself to half a
    gigabyte of it.
    """
    text = _read_meminfo()
    if text is None:
        return 0.0
    available = _kb_field(text, "MemAvailable")
    if available is None:
        available = _kb_field(text, "MemFree")
    return 0.0 if available is None else available / KB_PER_GB


def measure_bandwidth(
    mib: int = COPY_MIB, passes: int = COPY_PASSES
) -> Bandwidth | None:
    """Time a large memory copy and report GB/s.

    Deliberately *not* dmidecode: a nameplate DDR5-5600 figure is what the
    modules are rated at and says nothing about how many channels they end up
    populating, so it describes the parts and not this machine.

    Both buffers are allocated and touched before the clock starts. Copying
    into a freshly allocated object instead would time the allocator and the
    kernel's page faults — measured here at 1.5 GB/s against 17 GB/s for the
    same bytes into a warm buffer — which is a real cost but not the one the
    word "bandwidth" means. The best pass is taken rather than the mean,
    because everything that perturbs a copy loop (a scheduler switch, another
    process) can only make it slower: the fastest pass is the one least
    contaminated by something that is not memory.

    The buffer is sized to make the reading repeat. See ``COPY_MIB``: a 64 MiB
    copy on a shared machine varies by 44% run to run, which is not a number a
    comparison can be built on; 256 MiB brings that to 9%. On a machine with
    little free RAM the smaller buffer is used anyway and ``how`` records it,
    because taking half a gigabyte to measure memory is a poor trade on the
    rig that has least of it.
    """
    if mib == COPY_MIB and _spare_gb() < TIGHT_RAM_GB + 2 * mib / MIB_PER_GB:
        mib = COPY_MIB_TIGHT
    try:
        source = bytearray(mib * 1024 * 1024)
        target = bytearray(mib * 1024 * 1024)
    except (MemoryError, ValueError):
        return None
    target[:] = source  # fault both mappings in, off the clock
    moved = float(len(source))
    fastest = 0.0
    for _ in range(passes):
        start = time.perf_counter()
        target[:] = source
        elapsed = time.perf_counter() - start
        if elapsed > 0.0:
            fastest = max(fastest, moved / elapsed)
    if fastest <= 0.0:
        return None
    return Bandwidth(
        measured_gbps=round(fastest / 1e9, 1),
        how=f"in-process copy of {mib} MiB x{passes}, best pass, bytes copied/s",
    )


def _ssh(host: str, command: str) -> str:
    """Run one command on another machine, or say the machine is not there.

    ``BatchMode`` keeps a host whose key is not set up from parking the sweep
    on a password prompt: no credentials means unreachable, which is an
    outcome this can report.
    """
    output = _run(
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={CONNECT_TIMEOUT_S:g}",
        host,
        command,
        timeout=SSH_TIMEOUT_S,
    )
    if output is None:
        raise Unreachable(host)
    return output


def default_root() -> Path:
    """Where scans are kept. State, not config — these are measurements."""
    override = os.environ.get(SCAN_ROOT_ENV)
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "state"
    return base / "mcgyvr" / "scans"


def default_weights_dir() -> Path:
    """The path whose free space a scan reports when the caller names none."""
    override = os.environ.get(WEIGHTS_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cache" / "mcgyvr" / "weights"


def _field(text: str, key: str) -> str | None:
    """The value of a ``key: value`` line, from meminfo or lscpu alike.

    Matched on the whole key, so lscpu's ``NUMA node0 CPU(s)`` cannot be
    mistaken for its ``CPU(s)`` — which would make a NUMA machine's thread
    count whatever the last node reported.
    """
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


def _fingerprint(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _scan_machine() -> tuple[Machine, _Facts, _Notes]:
    """Identify the machine by something durable.

    Never by what was measured: a machine that gains a card is the same
    machine, and an id derived from its VRAM would file the next scan under a
    new name and silently lose the comparison that would have flagged it.
    """
    host = platform.node() or "localhost"
    kernel = platform.release()
    for path in MACHINE_ID_FILES:
        try:
            seed = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if seed:
            machine = Machine(id=_fingerprint(seed), host=host, kernel=kernel)
            return machine, (Fact(field="machine.id", how=f"sha256 of {path}"),), ()
    # A hostname is weaker — it can be changed, and two machines can share one
    # — but it is durable enough to file scans under, and saying so is better
    # than refusing to scan a machine without systemd.
    machine = Machine(id=_fingerprint(f"host:{host}"), host=host, kernel=kernel)
    return (
        machine,
        (Fact(field="machine.id", how="sha256 of hostname"),),
        (
            "Machine id: derived from the hostname — no /etc/machine-id. It is "
            "stable until the host is renamed, and a rename will read as a new "
            "machine rather than as a changed one.",
        ),
    )


def _parse_gpu_row(line: str) -> Gpu | None:
    """One ``index, name, total, used`` row, read from its ends inward.

    The query is this module's own and is four fields wide, but exactly one of
    those fields is free text a vendor writes, and vendors put commas in it —
    ``1, Tesla T4, Custom, 15360, 400`` is a real card printed as five fields.
    The row is therefore anchored at its ends, where the machine-generated
    values are: the index leads, the two memory numbers trail, and whatever
    lies between them is the name, comma and all. Splitting on commas and
    demanding exactly four fields instead would throw away a card that is
    present and shift every index after it.

    ``None`` means the row could not be read at all — a MIG or vGPU parent
    printing ``[N/A]`` for memory, or a future column order. The caller turns
    that into a note; it must never turn it into silence.
    """
    parts = [part.strip() for part in line.split(",")]
    if len(parts) < 4:
        return None
    try:
        index, total, used = int(parts[0]), int(parts[-2]), int(parts[-1])
    except ValueError:
        return None
    return Gpu(
        index=index,
        name=", ".join(parts[1:-2]),
        # Free is derived rather than queried: memory.free and memory.used are
        # sampled at different instants, and a total that does not equal used
        # plus free is a scan nobody can act on.
        vram=Vram(total_mib=total, used_mib=used, free_mib=max(total - used, 0)),
    )


def _scan_gpus() -> tuple[tuple[Gpu, ...], _Facts, _Notes]:
    """The cards nvidia-smi reports, and a note for every row it printed that
    this could not read.

    Rule 1 of this module in the hardest place to honour it: a row dropped in
    silence reads downstream as a machine with fewer cards, which is a
    different machine. It places a unit on the wrong card (a unit is bound by
    the index this list carries) and it makes the next :func:`compare` announce
    ``gpus: was 2, now 1`` — a pulled card that was never pulled. So an
    unreadable row costs a note, and the note names the row.
    """
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
                "GPU: not determined — nvidia-smi is absent or failed. This is "
                "a machine without an NVIDIA card as far as anything here can "
                "tell; AMD and Apple GPUs are invisible to it, so bind VRAM by "
                "hand on those rather than reading this as zero.",
            ),
        )
    gpus: list[Gpu] = []
    facts: list[Fact] = []
    notes: list[str] = []
    for line in output.strip().splitlines():
        if not line.strip():
            continue
        gpu = _parse_gpu_row(line)
        if gpu is None:
            notes.append(
                f"GPU: nvidia-smi printed a row this could not read, so that "
                f"card is missing from the scan: {line.strip()!r}. MIG and "
                f"vGPU rows report memory as [N/A] and land here. Read the "
                f"card list as incomplete rather than short: the indexes below "
                f"place a unit, and a change in their number reads as hardware "
                f"that was pulled."
            )
            continue
        gpus.append(gpu)
        facts.append(Fact(field=f"gpu[{gpu.index}].vram.total_mib", how=how))
        facts.append(
            Fact(field=f"gpu[{gpu.index}].vram.free_mib", how=f"{how} (total-used)")
        )
    if not gpus and not notes:
        return (), (), ("GPU: nvidia-smi answered but reported no device.",)
    return tuple(gpus), tuple(facts), tuple(notes)


def _scan_memory() -> tuple[Memory | None, _Facts, _Notes]:
    text = _read_meminfo()
    if text is None:
        return None, (), ("Memory: not determined — /proc/meminfo is unreadable.",)
    total = _kb_field(text, "MemTotal")
    available = _kb_field(text, "MemAvailable")
    if total is None:
        return None, (), ("Memory: /proc/meminfo carried no MemTotal.",)
    if available is None:
        # MemFree is the older kernels' answer and a worse one — it excludes
        # reclaimable cache — so it is used only as a fallback, and said so.
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
    memory = Memory(
        total_gb=round(total / KB_PER_GB, 1),
        available_gb=round(available / KB_PER_GB, 1),
    )
    facts = (
        Fact(field="memory.total_gb", how="/proc/meminfo MemTotal"),
        Fact(field="memory.available_gb", how=how_available),
    )
    return memory, facts, ()


def _scan_cpu() -> tuple[Cpu | None, _Facts, _Notes]:
    output = _run("lscpu")
    if output is None:
        return None, (), ("CPU: not determined — lscpu is absent or failed.",)
    threads = _int_field(output, "CPU(s)")
    per_socket = _int_field(output, "Core(s) per socket")
    sockets = _int_field(output, "Socket(s)") or 1
    if threads is None or per_socket is None:
        return (
            None,
            (),
            ("CPU: lscpu ran but did not report both CPU(s) and cores per socket.",),
        )
    cpu = Cpu(cores=per_socket * sockets, threads=threads)
    facts = (
        Fact(field="cpu.threads", how="lscpu CPU(s)"),
        Fact(field="cpu.cores", how="lscpu Core(s) per socket x Socket(s)"),
    )
    return cpu, facts, ()


def _scan_bandwidth() -> tuple[Bandwidth | None, _Facts, _Notes]:
    measured = measure_bandwidth()
    if measured is None:
        return (
            None,
            (),
            (
                "Memory bandwidth: not measured — the copy loop produced no "
                "usable timing. Left absent rather than filled in from a "
                "module nameplate, which describes the parts and not this "
                "machine.",
            ),
        )
    return measured, (Fact(field="bandwidth.measured_gbps", how=measured.how),), ()


def _scan_disk(weights_dir: Path | None) -> tuple[Disk, _Facts]:
    path = weights_dir if weights_dir is not None else default_weights_dir()
    free = _free_bytes(path)
    disk = Disk(path=path, free_gb=round(free / BYTES_PER_GB, 1))
    return disk, (Fact(field="disk.free_gb", how=f"free space on {path}"),)


def scan(weights_dir: Path | None = None) -> Scan:
    """Measure this machine. Never raises: a bare machine is a valid answer."""
    machine, machine_facts, machine_notes = _scan_machine()
    gpus, gpu_facts, gpu_notes = _scan_gpus()
    memory, memory_facts, memory_notes = _scan_memory()
    cpu, cpu_facts, cpu_notes = _scan_cpu()
    bandwidth, bandwidth_facts, bandwidth_notes = _scan_bandwidth()
    disk, disk_facts = _scan_disk(weights_dir)
    return Scan(
        machine=machine,
        gpus=gpus,
        memory=memory,
        cpu=cpu,
        bandwidth=bandwidth,
        disk=disk,
        notes=(
            *machine_notes,
            *gpu_notes,
            *memory_notes,
            *cpu_notes,
            *bandwidth_notes,
        ),
        facts=(
            *machine_facts,
            *gpu_facts,
            *memory_facts,
            *cpu_facts,
            *bandwidth_facts,
            *disk_facts,
        ),
    )


def machine_id(scan: Scan) -> str:
    """The key a machine's scans are filed under, here and on every other host."""
    return scan.machine.id


def local_machine_id() -> str:
    """The key *this* machine's scans are filed under, without measuring anything.

    :func:`scan` answers the same question, but it also times a memory copy and
    shells out twice to do it. A caller that only needs to know which record on
    disk describes the machine it is running on — resolving a source that says
    ``localhost`` to the scan filed under whatever this host calls itself — is
    asking about identity, not about hardware, and should not pay for a
    measurement to find out.

    Identity, not the name: :func:`_scan_machine` derives the id from
    ``/etc/machine-id`` where there is one, so this stays right across a
    rename, and two machines that happen to share a hostname stay apart.
    """
    machine, _, _ = _scan_machine()
    return machine.id


def write_scan(scan: Scan, root: Path | None = None) -> Path:
    """Record a scan under its machine's id, replacing that machine's last one."""
    base = root if root is not None else default_root()
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{machine_id(scan)}.json"
    path.write_text(scan.to_json(), encoding="utf-8")
    return path


def load_prior(machine_id: str, root: Path | None = None) -> Scan | None:
    """The last scan of a machine, or None if there has never been one.

    A record this cannot read is treated as absent too: the caller's answer to
    "no prior" is to record one, which repairs it.
    """
    base = root if root is not None else default_root()
    try:
        text = (base / f"{machine_id}.json").read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return Scan.from_json(text)
    except (ValueError, KeyError, TypeError):
        return None


def compare(scan: Scan, prior: Scan | None) -> tuple[Mismatch, ...]:
    """Stable fields that disagree with the last scan of the same machine.

    Only the fields that should not have moved. Used VRAM, available RAM and
    free disk are excluded by construction rather than by threshold: they are
    *supposed* to differ between two scans, so a difference in them is not
    evidence about the machine, and reporting it would bury the differences
    that are. What is left is the hardware changing under us — a card pulled, a
    DIMM failed back to single channel — which is worth interrupting someone
    for.
    """
    if prior is None:
        return ()
    found: list[Mismatch] = []

    if len(scan.gpus) != len(prior.gpus):
        found.append(
            Mismatch(field="gpus", prior=len(prior.gpus), measured=len(scan.gpus))
        )
    for now, was in zip(scan.gpus, prior.gpus, strict=False):
        if now.name != was.name:
            found.append(
                Mismatch(
                    field=f"gpu[{now.index}].name", prior=was.name, measured=now.name
                )
            )
        if now.vram.total_mib != was.vram.total_mib:
            found.append(
                Mismatch(
                    field=f"gpu[{now.index}].vram.total_mib",
                    prior=was.vram.total_mib,
                    measured=now.vram.total_mib,
                )
            )

    if scan.memory and prior.memory and scan.memory.total_gb != prior.memory.total_gb:
        found.append(
            Mismatch(
                field="memory.total_gb",
                prior=prior.memory.total_gb,
                measured=scan.memory.total_gb,
            )
        )

    if scan.cpu and prior.cpu:
        if scan.cpu.cores != prior.cpu.cores:
            found.append(
                Mismatch(
                    field="cpu.cores", prior=prior.cpu.cores, measured=scan.cpu.cores
                )
            )
        if scan.cpu.threads != prior.cpu.threads:
            found.append(
                Mismatch(
                    field="cpu.threads",
                    prior=prior.cpu.threads,
                    measured=scan.cpu.threads,
                )
            )

    if scan.bandwidth and prior.bandwidth:
        was_gbps = prior.bandwidth.measured_gbps
        now_gbps = scan.bandwidth.measured_gbps
        drift = abs(now_gbps - was_gbps)
        if was_gbps > 0 and drift > BANDWIDTH_TOLERANCE * was_gbps:
            found.append(
                Mismatch(
                    field="bandwidth.measured_gbps",
                    prior=was_gbps,
                    measured=now_gbps,
                )
            )

    return tuple(found)


def scan_over(reach: Reach) -> Scan:
    """Scan the machine ``reach`` reaches, whichever side of the wire it is on.

    The remote branch runs this same module over there and reads its answer
    back, which is the only way the numbers can be measured rather than
    inferred — and the reason the two branches return one type.
    """
    if reach.host is None:
        return scan()
    return Scan.from_json(_ssh(reach.host, REMOTE_COMMAND))


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
        except Unreachable:
            unreachable.append(host)
    return Sweep(scans=tuple(scans), unreachable=tuple(unreachable))
