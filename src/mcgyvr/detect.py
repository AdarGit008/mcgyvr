"""What this machine can actually run, detected without benchmarking it.

``mcgyvr init`` proposes worker bindings from the shipped capability table
(``data/capability-table.json``); this module supplies the other half of
that decision — what hardware and which backends are actually here. It
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

Probes run concurrently against a short timeout, so an endpoint that
accepts a connection and then hangs costs the timeout once rather than
serially. This module only observes. Turning observations into a proposed
ladder is a separate concern and does not live here.
"""

from __future__ import annotations

import json
import os
import platform
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


@dataclass(frozen=True)
class Endpoint:
    """A place a backend might be listening, and the protocol to ask in."""

    name: str
    base_url: str
    api: str  # "ollama" or "openai"


# Default ports each backend ships with. Identification is by port
# convention, which is a guess about identity but not about capability:
# what matters downstream is the wire protocol and the model list, and
# both are read from the answer rather than assumed.
DEFAULT_ENDPOINTS: tuple[Endpoint, ...] = (
    Endpoint("ollama", "http://localhost:11434", "ollama"),
    Endpoint("llama-server", "http://localhost:8080", "openai"),
    Endpoint("vllm", "http://localhost:8000", "openai"),
    Endpoint("lmstudio", "http://localhost:1234", "openai"),
    Endpoint("tgi", "http://localhost:3000", "openai"),
)


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


def probe(endpoint: Endpoint, timeout: float = PROBE_TIMEOUT_S) -> Backend | None:
    """Ask one endpoint what it is serving. None means nothing usable there."""
    path = "/api/tags" if endpoint.api == "ollama" else "/v1/models"
    url = endpoint.base_url.rstrip("/") + path
    payload = _get_json(url, timeout)
    if payload is None:
        return None
    return Backend(
        name=endpoint.name,
        base_url=endpoint.base_url,
        api=endpoint.api,
        models=_models_from(payload, endpoint.api),
        how=f"answered GET {path} at {endpoint.base_url} within {timeout:g}s",
    )


def probe_all(
    endpoints: Sequence[Endpoint] = DEFAULT_ENDPOINTS,
    timeout: float = PROBE_TIMEOUT_S,
) -> tuple[Backend, ...]:
    """Probe every endpoint at once, so the wall clock is one timeout."""
    if not endpoints:
        return ()
    with ThreadPoolExecutor(max_workers=len(endpoints)) as pool:
        results = pool.map(lambda e: probe(e, timeout), endpoints)
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
    """Whether a usable Docker daemon is here — it decides the sandbox mode."""
    if shutil.which("docker") is None:
        return False, "docker is not on PATH"
    output = _run(["docker", "info", "--format", "{{.ServerVersion}}"])
    if output is None or not output.strip():
        return False, "docker is on PATH but its daemon did not answer"
    return True, f"docker info reported server {output.strip()}"


def detect(
    endpoints: Sequence[Endpoint] = DEFAULT_ENDPOINTS,
    timeout: float = PROBE_TIMEOUT_S,
) -> Detection:
    """Survey the machine. Never raises: a bare machine is a valid answer."""
    gpus, gpu_notes = detect_gpus()
    ram_gb, ram_how = detect_ram_gb()
    docker, docker_how = detect_docker()
    backends = probe_all(endpoints, timeout)
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
        tried = ", ".join(e.base_url for e in endpoints)
        notes.append(
            f"No local backend answered. Tried: {tried or '(none)'}. This is "
            f"a supported install — the ladder degrades to whatever is bound "
            f"by hand — but nothing local can be proposed from it."
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
