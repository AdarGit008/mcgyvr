"""What can actually run the work, detected without benchmarking it.

``mcgyvr init`` proposes worker bindings from the shipped capability table
(``data/capability-table.json``); this module supplies the other half of
that decision — what hardware and which backends are actually reachable. It
measures nothing: benchmarking would turn a 30-second install into an hour,
which is the whole reason the table is shipped pre-measured.

Two rules shape everything below:

1. **Absence is an outcome, not an error.** No GPU, no Docker and no
   reachable backend is a supported machine — it constrains the proposal
   rather than failing it. Nothing here raises on a missing tool.
2. **Every fact carries how it was found.** A detected value with no
   provenance is indistinguishable from a guess, and the proposal built on
   top of it has to be explainable to someone whose machine it describes.
   What could *not* be determined is recorded too, in ``notes`` — silence
   about a failed probe reads as "absent" when it may mean "unknown".

**The host is an input, not a literal (#161).** The port conventions below
are what a backend ships with; the machine they are asked of is supplied by
the caller. ``localhost`` is the default, so a single-machine install is
unchanged, but the deployment this project exists for — an agent on a
laptop, offloading to rigs elsewhere — is expressible rather than invisible.
The hardware half of detection stays local by definition: ``nvidia-smi``
here describes this machine, and a remote rig's card is not something this
module can see. What it *can* see of a remote rig — the models that rig
reports holding — is the evidence the proposal uses instead, and unlike a
VRAM estimate it cannot be wrong about which machine it describes.

A probed host is identified by name in every backend it yields, because with
more than one host in play "ollama answered" no longer identifies anything.
Names stay bare for a single-host sweep so the ordinary install reads the way
it always did.

**Asking and dispatching are two different questions (#164).** A backend is
probed on whichever protocol enumerates what it holds, and bound on whichever
protocol work should later be sent over. For every backend here but one those
are the same answer. Ollama is the exception and the reason the fields are
separate: its native listing is the only one that includes models pulled but
not loaded, while its native *generation* path is the one CAV-01 invalidates.

Probes run concurrently against a short timeout, so an endpoint that
accepts a connection and then hangs costs the timeout once rather than
serially — and a sweep of two hosts costs the same wall clock as one. This
module only observes. Turning observations into a proposed ladder is a
separate concern and does not live here.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import urllib.error
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

# The machine a sweep asks about when the caller names none. Keeping the
# single-machine install on exactly the path it has always taken is an
# acceptance criterion of #161, not a courtesy.
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
    is qualified with the host only when a sweep covers more than one, so an
    ordinary install keeps the bare names it has always had.
    """

    name: str
    base_url: str
    api: str  # how to ASK: "ollama" or "openai"
    host: str = DEFAULT_HOST
    kind: str = ""  # the backend convention: "ollama", "vllm", ... (default: name)
    binds_as: str = ""  # how to DISPATCH later; defaults to `api`

    def __post_init__(self) -> None:
        # `kind` is what the server IS; `name` is what it will be called. They
        # part company the moment a sweep covers two hosts, and the capability
        # table's `requires_backend` matches on the former — a model measured
        # on Ollama is measured on Ollama whether the source is called
        # `ollama` or `srv2_ollama`.
        if not self.kind:
            object.__setattr__(self, "kind", self.name)
        if not self.binds_as:
            object.__setattr__(self, "binds_as", binds_as_for(self.kind, self.api))


# Default ports each backend ships with, and for each: how to ASK it what it
# holds, then how to DISPATCH to it. Identification is by port convention,
# which is a guess about identity but not about capability: what matters
# downstream is the wire protocol and the model list, and both are read from
# the answer rather than assumed.
#
# **Ollama is asked one way and bound another, and that is the point (#164).**
# Its native `/api/tags` is the only endpoint that enumerates models that are
# *pulled but not loaded*, which is exactly the inventory a proposal needs. Its
# native `/api/generate`, though, is the path CAV-01 is a record of — it scored
# `qwen2.5-coder:7b` at 32.3% against a true 84.1%, so every completion from it
# is marked `quality_safe=False` and a quality-sensitive request is refused
# outright. The same port also serves the OpenAI-compatible shape, with the same
# model ids and no caveat. Asking natively and dispatching compatibly is not a
# compromise between the two; it is each protocol used for the thing it is
# actually better at.
PORT_CONVENTIONS: tuple[tuple[str, int, str, str], ...] = (
    ("ollama", 11434, "ollama", "openai"),
    ("llama-server", 8080, "openai", "openai"),
    ("vllm", 8000, "openai", "openai"),
    ("lmstudio", 1234, "openai", "openai"),
    ("tgi", 3000, "openai", "openai"),
)


def binds_as_for(kind: str, api: str) -> str:
    """The protocol to dispatch to ``kind`` on, given how it was asked.

    Reads the one convention table, so every construction path agrees. That
    matters more than it looks: the difference between asking Ollama natively
    and dispatching to it natively is a measured 32.3% against 84.1%, and a
    :class:`Backend` built by hand — in a test, or by a future caller that is
    not :func:`probe` — silently taking the caveated path would be a trap
    rather than a default.
    """
    for name, _, _, binds in PORT_CONVENTIONS:
        if name == kind:
            return binds
    return api


def _host_token(host: str) -> str:
    """A host as a name segment: safe in a YAML key and in a tier name.

    A tailnet address (``100.69.72.51``) and a DNS name
    (``srv1.tailbaf744.ts.net``) both have to survive becoming a config key
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
    conventions: Sequence[tuple[str, int, str, str]] = PORT_CONVENTIONS,
) -> tuple[ProbeTarget, ...]:
    """Expand hosts into the candidate endpoints to sweep on each.

    The cross product of hosts and port conventions, which is the whole of
    what #161 changed: the ports were already a table, and the host was the
    literal. A host is a bare name or address — ``srv1``,
    ``100.69.72.51`` — and never a port, because identification here is *by*
    port convention and a port nobody conventionally uses carries no claim
    about which protocol answers on it. An endpoint on a non-standard port is
    bound by hand, the same as it is today.

    Duplicate hosts collapse, so naming the same rig twice does not probe it
    twice or mint two sources for it.
    """
    unique = tuple(dict.fromkeys(h.strip() for h in hosts if h.strip()))
    qualify = len(unique) > 1
    targets: list[ProbeTarget] = []
    for host in unique:
        for name, port, api, binds_as in conventions:
            targets.append(
                ProbeTarget(
                    name=f"{_host_token(host)}_{name}" if qualify else name,
                    base_url=f"http://{host}:{port}",
                    api=api,
                    host=host,
                    kind=name,
                    binds_as=binds_as,
                )
            )
    return tuple(targets)


DEFAULT_PROBE_TARGETS: tuple[ProbeTarget, ...] = targets_for()


@dataclass(frozen=True)
class Gpu:
    name: str
    vram_gb: float
    how: str


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
    binds_as: str = ""  # the protocol a config should dispatch on; see #164

    def __post_init__(self) -> None:
        if not self.kind:
            object.__setattr__(self, "kind", self.name)
        if not self.binds_as:
            object.__setattr__(self, "binds_as", binds_as_for(self.kind, self.api))

    @property
    def bound_on_another_protocol(self) -> bool:
        """Whether this will be dispatched to differently from how it answered.

        True for Ollama and nothing else today. Surfaced rather than left
        implicit because a config saying ``api: openai`` for a source that
        `detect` called Ollama looks like a mistake until the reason is given.
        """
        return self.binds_as != self.api

    @property
    def is_local(self) -> bool:
        """Whether this backend is on the machine mcgyvr is running on.

        Decided by the name the user gave, not by resolving the address: a
        rig reachable as ``localhost`` through an SSH tunnel really is being
        treated as local by everything else here, and one named by its
        tailnet address is not, whatever it resolves to.
        """
        return self.host in (DEFAULT_HOST, "127.0.0.1", "::1", "[::1]")

    def has_model(self, model_id: str) -> bool:
        """Whether this backend already holds a model, by exact id or by tag.

        Ollama reports `qwen2.5-coder:7b`; an OpenAI-compatible server may
        report a path or a bare name for the same weights. An exact match is
        the only claim made here — a near match is reported as absent, since
        proposing a pull that turns out to be unnecessary is cheaper than
        binding a model that is not there.
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
        """VRAM of the biggest single card, or None when there is no GPU.

        Deliberately not a sum: a model runs on one card, so two 6 GB cards
        are two 6 GB decisions, not one 12 GB decision. Multi-GPU sharding
        would change that and is not something this detects.
        """
        return max((g.vram_gb for g in self.gpus), default=None)

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

        The fact that decides whether this machine's own GPU is the right
        thing to size a proposal against: with work being served elsewhere,
        the local card is not a constraint on it.
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

    Every failure mode here — refused, timed out, 404, not JSON — means the
    same thing to the caller: nothing usable is listening.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None


def _models_from(payload: Any, api: str) -> tuple[str, ...]:
    """Pull model ids out of either wire protocol's listing."""
    if not isinstance(payload, dict):
        return ()
    rows = payload.get("models") if api == "ollama" else payload.get("data")
    if not isinstance(rows, list):
        return ()
    key = "name" if api == "ollama" else "id"
    found = [
        row[key]
        for row in rows
        if isinstance(row, dict) and isinstance(row.get(key), str)
    ]
    return tuple(dict.fromkeys(found))  # de-duplicated, order preserved


def probe(target: ProbeTarget, timeout: float = PROBE_TIMEOUT_S) -> Backend | None:
    """Ask one target what it is serving. None means nothing usable there."""
    path = "/api/tags" if target.api == "ollama" else "/v1/models"
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
        binds_as=target.binds_as,
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


def detect_gpus() -> tuple[tuple[Gpu, ...], tuple[str, ...]]:
    """Detect NVIDIA GPUs. Anything else is reported as undetermined."""
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
    for line in output.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 2:
            continue
        try:
            mib = float(parts[1])
        except ValueError:
            continue
        gpus.append(
            Gpu(
                name=parts[0],
                vram_gb=round(mib / MIB_PER_GB, 1),
                how="nvidia-smi --query-gpu=name,memory.total",
            )
        )
    if not gpus:
        return (), ("GPU: nvidia-smi ran but reported no device.",)
    return tuple(gpus), ()


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
