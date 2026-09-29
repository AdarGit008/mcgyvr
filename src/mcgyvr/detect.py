"""What can actually run the work, detected without benchmarking it.

``mcgyvr init`` binds the models that running servers list; this module finds
those servers and what each one lists, and the cards this machine has. It
measures nothing: benchmarking would turn a 30-second install into an hour.

Two rules shape everything below:

1. **Absence is an outcome, not an error.** No GPU, no Docker and no
   reachable backend is a supported machine — it constrains the proposal
   rather than failing it. Nothing here raises on a missing tool.
2. **Every fact carries how it was found.** A detected value with no
   provenance is indistinguishable from a guess, and the proposal built on
   top of it has to be explainable to someone whose machine it describes.
   What could *not* be determined is recorded too, in ``notes`` — silence
   about a failed probe reads as "absent" when it may mean "unknown".

**The host is an input, not a literal.** The port conventions below are what
a backend ships with; the machine they are asked of is supplied by the caller.
``localhost`` is the default, and the deployment this project exists for — an
agent on a laptop, offloading to rigs elsewhere — is expressible.
The hardware half of detection stays local by definition: ``nvidia-smi``
here describes this machine, and a remote rig's card is not something this
module can see. What it *can* see of a remote rig — the models that rig
reports holding — is the evidence the proposal uses instead, and unlike a
VRAM estimate it cannot be wrong about which machine it describes.

A probed host is identified by name in every backend it yields, because with
more than one host in play "a backend answered" identifies nothing.
Names stay bare for a single-host sweep.

Every backend here is asked and dispatched to on the same protocol.

Probes run concurrently against a short timeout, so an endpoint that
accepts a connection and then hangs costs the timeout once rather than
serially — and a sweep of two hosts costs the same wall clock as one. This
module only observes. Turning observations into a proposed ladder is a
separate concern and does not live here.
"""

from __future__ import annotations

import http.client
import json
import math
import os
import platform
import re
import shutil
import subprocess
import urllib.request
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

# An unreachable port fails fast; a reachable one that hangs costs this
# once, because probes run concurrently.
PROBE_TIMEOUT_S = 1.0
COMMAND_TIMEOUT_S = 5.0

MIB_PER_GB = 1024.0

# The machine a sweep asks about when the caller names none.
DEFAULT_HOST = "localhost"


@dataclass(frozen=True)
class ProbeTarget:
    """A place a backend might be listening, and the protocol to ask in.

    A *candidate* address, not a resolved one: nothing is known to be here
    until :func:`probe` gets an answer. Distinct from
    :class:`mcgyvr.pool.Endpoint`, which is somewhere a rung is configured to
    run and exists only once there is a config to resolve.

    ``host`` is carried alongside ``base_url`` rather than parsed back out of
    it, because it is what the user named and what every downstream report
    identifies the machine by. ``name`` is what a source will be called; it
    is qualified with the host only when a sweep covers more than one, so a
    single-host install keeps bare names.
    """

    name: str
    base_url: str
    api: str  # the wire protocol, asked and dispatched alike: "openai"
    host: str = DEFAULT_HOST
    kind: str = ""  # the backend convention: "vllm", "llama-server", ...

    def __post_init__(self) -> None:
        # `kind` is what the server IS; `name` is what it will be called. They
        # part company the moment a sweep covers two hosts, and the capability
        # table's `requires_backend` matches on the former — a model measured
        # on vLLM is measured on vLLM whether the source is called `vllm` or
        # `box_example_vllm`.
        if not self.kind:
            object.__setattr__(self, "kind", self.name)


# Default ports each backend ships with, and the one wire protocol it is asked
# and dispatched to on. Identification is by port convention, which is a guess
# about identity but not about capability: the model list is read from the
# answer rather than assumed.
PORT_CONVENTIONS: tuple[tuple[str, int, str], ...] = (
    ("llama-server", 8080, "openai"),
    ("vllm", 8000, "openai"),
    ("lmstudio", 1234, "openai"),
    ("tgi", 3000, "openai"),
)


def _host_token(host: str) -> str:
    """A host as a name segment: safe in a YAML key and in a tier name.

    An address (``192.0.2.10``) and a DNS name
    (``box.example.net``) both have to survive becoming a config key
    someone edits by hand, so the separators become underscores and the
    leading character is guaranteed non-numeric. The result identifies the
    host to a reader; it is not required to be reversible.
    """
    token = re.sub(r"[^A-Za-z0-9]+", "_", host).strip("_").lower()
    if not token:
        return "host"
    return token if token[0].isalpha() else f"h{token}"


def targets_for(
    hosts: Sequence[str] = (DEFAULT_HOST,),
    conventions: Sequence[tuple[str, int, str]] = PORT_CONVENTIONS,
) -> tuple[ProbeTarget, ...]:
    """Expand hosts into the candidate endpoints to sweep on each.

    The cross product of hosts and port conventions. A host is a bare name or
    address — ``box.example``, ``192.0.2.10`` — and never a port, because
    identification here is *by* port convention and a port nobody
    conventionally uses carries no claim about which protocol answers on it.
    An endpoint on a non-standard port is bound by hand.

    Duplicate hosts collapse, so naming the same rig twice does not probe it
    twice or mint two sources for it.
    """
    unique = tuple(dict.fromkeys(h.strip() for h in hosts if h.strip()))
    qualify = len(unique) > 1
    targets: list[ProbeTarget] = []
    for host in unique:
        for name, port, api in conventions:
            targets.append(
                ProbeTarget(
                    name=f"{_host_token(host)}_{name}" if qualify else name,
                    base_url=f"http://{host}:{port}",
                    api=api,
                    host=host,
                    kind=name,
                )
            )
    return tuple(targets)


DEFAULT_PROBE_TARGETS: tuple[ProbeTarget, ...] = targets_for()


#: How a note begins for a card that is listed but whose memory size the card
#: tool printed as not available: the card is there, its size is not known.
GPU_SIZE_UNDETERMINED = "GPU: memory size not determined"
#: How a note begins for a row the card tool printed that could not be read as
#: a card at all. The note quotes the row, so the card is named, not dropped.
GPU_ROW_NOT_READ = "GPU: nvidia-smi printed a row that could not be read as a card"
#: The most characters of the card tool's own text a note quotes. A row may be
#: of any length, and a note is printed and written into a setup, so a longer
#: quote keeps both ends and not the middle.
ROW_QUOTED_AT_MOST = 200


def _quoted(text: str) -> str:
    """``text`` quoted, cut in the middle when longer than the bound."""
    shown = repr(text)
    if len(shown) <= ROW_QUOTED_AT_MOST:
        return shown
    keep = (ROW_QUOTED_AT_MOST - len(" ... ")) // 2
    return f"{shown[:keep]} ... {shown[-keep:]}"


@dataclass(frozen=True)
class Gpu:
    """One card. ``vram_gb`` is ``None`` when its size could not be determined.

    A card of undetermined size is still a card: it is listed, and a note says
    its size is unknown. It takes no part in sizing (see
    :attr:`Detection.largest_vram_gb`), because a size nobody read is not a
    size to fit a model against.
    """

    name: str
    vram_gb: float | None
    how: str

    @property
    def size(self) -> str:
        """The card's memory as a reader should see it."""
        if self.vram_gb is None:
            return "memory size not determined"
        return f"{self.vram_gb:g} GB"


@dataclass(frozen=True)
class Backend:
    """A backend that answered, with what it said it can serve."""

    name: str
    base_url: str
    api: str
    models: tuple[str, ...]
    how: str
    host: str = DEFAULT_HOST
    kind: str = ""  # the backend convention; see ProbeTarget.kind

    def __post_init__(self) -> None:
        if not self.kind:
            object.__setattr__(self, "kind", self.name)

    @property
    def is_local(self) -> bool:
        """Whether this backend is on the machine mcgyvr is running on.

        Decided by the name the user gave, not by resolving the address: a
        rig reachable as ``localhost`` through an SSH tunnel really is being
        treated as local by everything else here, and one named by its
        network address is not, whatever it resolves to.
        """
        return self.host in (DEFAULT_HOST, "127.0.0.1", "::1", "[::1]")

    def has_model(self, model_id: str) -> bool:
        """Whether this backend already holds a model, by exact id only.

        A server may report a path, a bare name or a tagged name for the same
        weights, and they are not interchangeable. An exact match is the only
        claim made here — a near match is reported as absent.
        """
        return model_id in self.models


@dataclass(frozen=True)
class Detection:
    """What was found, how it was found, and what could not be determined."""

    gpus: tuple[Gpu, ...] = ()
    cpu_count: int | None = None
    ram_gb: float | None = None
    backends: tuple[Backend, ...] = ()
    docker: bool = False
    provenance: Mapping[str, str] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    @property
    def has_gpu(self) -> bool:
        return bool(self.gpus)

    @property
    def largest_vram_gb(self) -> float | None:
        """VRAM of the biggest single card whose size is known, else None.

        Deliberately not a sum: a model runs on one card, so several cards
        are one decision per card, never one decision over their total.
        Multi-GPU sharding would change that and is not something this detects.

        A card of undetermined size takes no part: it is not the largest, and
        with no card of known size this is None, as for a machine without a
        card. The card is still in :attr:`gpus` and named in :attr:`notes`.
        """
        sizing = self.sizing_gpu
        return None if sizing is None else sizing.vram_gb

    @property
    def sizing_gpu(self) -> Gpu | None:
        """The card :attr:`largest_vram_gb` reads: the biggest of known size.

        Of cards of one size, the first the tool listed. None when no card's
        size is known. Whatever names the card that sizing used reads it here,
        so it cannot name one card while the sizing used another.
        """
        sized = [g for g in self.gpus if g.vram_gb is not None]
        return max(sized, key=lambda g: g.vram_gb or 0.0, default=None)

    def backend(self, name: str) -> Backend | None:
        return next((b for b in self.backends if b.name == name), None)

    def models_present(self) -> frozenset[str]:
        """Every model id any reachable backend reports holding."""
        return frozenset(m for b in self.backends for m in b.models)

    @property
    def hosts_answering(self) -> tuple[str, ...]:
        """Every host that answered on at least one endpoint, in probe order."""
        return tuple(dict.fromkeys(b.host for b in self.backends))

    @property
    def has_remote_backend(self) -> bool:
        """Whether any reachable backend is on another machine.

        Such a backend serves from that machine's card, which this machine's
        card tool does not see.
        """
        return any(not b.is_local for b in self.backends)


def _run(command: Sequence[str]) -> str | None:
    """Run a command, returning its stdout or None if it cannot be run."""
    if shutil.which(command[0]) is None:
        return None
    try:
        done = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _get_json(url: str, timeout: float) -> Any | None:
    """GET a JSON document, returning None on any failure whatsoever.

    Every failure mode here — refused, timed out, 404, not JSON, a status line
    that is not one, a body that ends before the length it stated — means the
    same thing to the caller: nothing usable is listening. The last two are
    ``http.client.HTTPException``, which is not an ``OSError``. JSON nested
    deeper than the reader follows raises ``RecursionError``, which is neither,
    and means the same.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, http.client.HTTPException, RecursionError):
        return None


def _models_from(payload: Any, api: str) -> tuple[str, ...]:
    """Pull model ids out of the listing. ``api`` names the protocol asked."""
    if not isinstance(payload, dict):
        return ()
    rows = payload.get("data")
    if not isinstance(rows, list):
        return ()
    key = "id"
    found = [
        row[key]
        for row in rows
        if isinstance(row, dict) and isinstance(row.get(key), str)
    ]
    return tuple(dict.fromkeys(found))  # de-duplicated, order preserved


def probe(target: ProbeTarget, timeout: float = PROBE_TIMEOUT_S) -> Backend | None:
    """Ask one target what it is serving. None means nothing usable there."""
    path = "/v1/models"
    url = target.base_url.rstrip("/") + path
    payload = _get_json(url, timeout)
    if payload is None:
        return None
    return Backend(
        name=target.name,
        base_url=target.base_url,
        api=target.api,
        models=_models_from(payload, target.api),
        how=f"answered GET {path} at {target.base_url} within {timeout:g}s",
        host=target.host,
        kind=target.kind,
    )


def probe_all(
    targets: Sequence[ProbeTarget] = DEFAULT_PROBE_TARGETS,
    timeout: float = PROBE_TIMEOUT_S,
) -> tuple[Backend, ...]:
    """Probe every target at once, so the wall clock is one timeout."""
    if not targets:
        return ()
    with ThreadPoolExecutor(max_workers=len(targets)) as pool:
        results = pool.map(lambda t: probe(t, timeout), targets)
    return tuple(b for b in results if b is not None)


def _is_not_available(value: str) -> bool:
    """Whether the card tool printed a field as a value it could not give.

    It prints those bracketed — ``[N/A]``, ``[Not Supported]`` — in place of
    the number, and a bracketed field is never a number.
    """
    return value.startswith("[") and value.endswith("]")


def detect_gpus() -> tuple[tuple[Gpu, ...], tuple[str, ...]]:
    """Detect NVIDIA GPUs. Anything else is reported as undetermined.

    Every row the card tool prints becomes a card or a note. A row is anchored
    at its end, where the size is: the last field is the size and everything
    before it is the name, commas and all. A size printed as not available
    makes a card of undetermined size, with a note. A row with no size field,
    or a size that is neither a number nor not available, is quoted in a note.
    """
    how = "nvidia-smi --query-gpu=name,memory.total"
    output = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total",
            "--format=csv,noheader,nounits",
        ]
    )
    if output is None:
        return (), (
            "GPU: not determined — nvidia-smi is absent or failed. AMD and "
            "Apple GPUs are not detected; on those machines bind VRAM by "
            "hand rather than trusting a zero here.",
        )

    gpus: list[Gpu] = []
    notes: list[str] = []
    for line in output.strip().splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(",")]
        name, size = ", ".join(parts[:-1]), parts[-1]
        if len(parts) >= 2 and name and _is_not_available(size):
            gpus.append(Gpu(name=name, vram_gb=None, how=how))
            notes.append(
                f"{GPU_SIZE_UNDETERMINED} for {_quoted(name)}: nvidia-smi "
                f"printed its memory.total as {_quoted(size)}. The card is "
                f"listed, but no model is sized against it: bind a unit to it by "
                f"hand, stating the card room it needs as `room_mib`."
            )
            continue
        try:
            mib = float(size) if len(parts) >= 2 and name else math.nan
        except ValueError:
            mib = math.nan
        if not math.isfinite(mib) or mib < 0:
            notes.append(
                f"{GPU_ROW_NOT_READ}, so that card is missing from the list: "
                f"{_quoted(line.strip())}. Read the card list as incomplete, not short."
            )
            continue
        gpus.append(Gpu(name=name, vram_gb=round(mib / MIB_PER_GB, 1), how=how))
    if not gpus and not notes:
        return (), ("GPU: nvidia-smi ran but reported no device.",)
    if not gpus:
        return (), (
            "GPU: nvidia-smi ran but reported no device this could read.",
            *notes,
        )
    return tuple(gpus), tuple(notes)


def detect_ram_gb() -> tuple[float | None, str]:
    """Total system RAM, as fallback context when there is no GPU."""
    if platform.system() == "Darwin":
        output = _run(["sysctl", "-n", "hw.memsize"])
        if output and output.strip().isdigit():
            return round(int(output.strip()) / 1024**3, 1), "sysctl -n hw.memsize"
        return None, "not determined — sysctl hw.memsize unreadable"

    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    kib = float(line.split()[1])
                    return round(kib / 1024**2, 1), "/proc/meminfo MemTotal"
    except (OSError, IndexError, ValueError):
        pass
    return None, "not determined — /proc/meminfo unreadable"


def detect_docker() -> tuple[bool, str]:
    """Whether a usable Docker daemon is here — it decides the sandbox mode.

    "Here" is this machine. With the environment pointing docker at another
    daemon nothing is probed — the `docker info` would go wherever it points,
    a rig included — and the answer is no, carrying the sandbox's refusal.
    """
    from mcgyvr.sandbox.image import foreign_daemon

    refusal = foreign_daemon()
    if refusal is not None:
        return False, refusal
    if shutil.which("docker") is None:
        return False, "docker is not on PATH"
    output = _run(["docker", "info", "--format", "{{.ServerVersion}}"])
    if output is None or not output.strip():
        return False, "docker is on PATH but its daemon did not answer"
    return True, f"docker info reported server {output.strip()}"


def detect(
    targets: Sequence[ProbeTarget] = DEFAULT_PROBE_TARGETS,
    timeout: float = PROBE_TIMEOUT_S,
) -> Detection:
    """Survey the machine. Never raises: a bare machine is a valid answer."""
    gpus, gpu_notes = detect_gpus()
    ram_gb, ram_how = detect_ram_gb()
    docker, docker_how = detect_docker()
    backends = probe_all(targets, timeout)
    cpu_count = os.cpu_count()

    provenance: dict[str, str] = {
        "cpu_count": "os.cpu_count()",
        "ram_gb": ram_how,
        "docker": docker_how,
    }
    for gpu in gpus:
        provenance[f"gpu:{gpu.name}"] = gpu.how
    for backend in backends:
        provenance[f"backend:{backend.name}"] = backend.how

    notes = list(gpu_notes)
    if not backends:
        tried = ", ".join(t.base_url for t in targets)
        hosts = tuple(dict.fromkeys(t.host for t in targets))
        where = (
            "No backend answered on any host swept"
            if hosts and hosts != (DEFAULT_HOST,)
            else "No local backend answered"
        )
        notes.append(
            f"{where}. Tried: {tried or '(none)'}. This is "
            f"a supported install — the ladder degrades to whatever is bound "
            f"by hand — but nothing can be proposed from it. A rig elsewhere "
            f"is swept only when it is named: `mcgyvr detect --host <name>`."
        )
    if not docker:
        notes.append(
            f"Sandbox falls back to a temp directory ({docker_how}). That is "
            f"the explicitly weaker mode: acceptance commands are arbitrary "
            f"shell from a contract."
        )
    if cpu_count is None:
        provenance.pop("cpu_count")
        notes.append("CPU count: not determined — os.cpu_count() returned None.")
    if ram_gb is None:
        provenance.pop("ram_gb")

    return Detection(
        gpus=gpus,
        cpu_count=cpu_count,
        ram_gb=ram_gb,
        backends=backends,
        docker=docker,
        provenance=provenance,
        notes=tuple(notes),
    )
