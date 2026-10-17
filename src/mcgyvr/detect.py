""

from __future__ import annotations

import http.client
import json
import os
import re
import shutil
import subprocess
import urllib.request
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

#
#
PROBE_TIMEOUT_S = 1.0
COMMAND_TIMEOUT_S = 5.0

MIB_PER_GB = 1024.0

#
DEFAULT_HOST = "localhost"

#
#
LOCAL_HOSTS = (DEFAULT_HOST, "127.0.0.1", "::1", "[::1]")


def is_local_host(host: str) -> bool:
    ""
    return host in LOCAL_HOSTS


@dataclass(frozen=True)
class ProbeTarget:
    ""

    name: str
    base_url: str
    api: str  #
    host: str = DEFAULT_HOST
    kind: str = ""  #

    def __post_init__(self) -> None:
        #
        #
        #ed
        #
        #
        if not self.kind:
            object.__setattr__(self, "kind", self.name)


#
#
#
#
PORT_CONVENTIONS: tuple[tuple[str, int, str], ...] = (
    ("llama-server", 8080, "openai"),
    ("vllm", 8000, "openai"),
    ("lmstudio", 1234, "openai"),
    ("tgi", 3000, "openai"),
)


def _host_token(host: str) -> str:
    ""
    token = re.sub(r"[^A-Za-z0-9]+", "_", host).strip("_").lower()
    if not token:
        return "host"
    return token if token[0].isalpha() else f"h{token}"


def targets_for(
    hosts: Sequence[str] = (DEFAULT_HOST,),
    conventions: Sequence[tuple[str, int, str]] = PORT_CONVENTIONS,
) -> tuple[ProbeTarget, ...]:
    ""
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


#
#
GPU_SIZE_UNDETERMINED = "GPU: memory size not determined"
#
#
GPU_ROW_NOT_READ = "GPU: nvidia-smi printed a row that could not be read as a card"
#
#
#
ROW_QUOTED_AT_MOST = 200


def _quoted(text: str) -> str:
    ""
    shown = repr(text)
    if len(shown) <= ROW_QUOTED_AT_MOST:
        return shown
    keep = (ROW_QUOTED_AT_MOST - len(" ... ")) // 2
    return f"{shown[:keep]} ... {shown[-keep:]}"


@dataclass(frozen=True)
class Gpu:
    ""

    name: str
    vram_gb: float | None
    how: str

    @property
    def size(self) -> str:
        ""
        if self.vram_gb is None:
            return "memory size not determined"
        return f"{self.vram_gb:g} GB"


@dataclass(frozen=True)
class Backend:
    ""

    name: str
    base_url: str
    api: str
    models: tuple[str, ...]
    how: str
    host: str = DEFAULT_HOST
    kind: str = ""  #
    #
    #
    #
    #
    #
    window: int | None = None

    def __post_init__(self) -> None:
        if not self.kind:
            object.__setattr__(self, "kind", self.name)

    @property
    def is_local(self) -> bool:
        ""
        return is_local_host(self.host)

    def has_model(self, model_id: str) -> bool:
        ""
        return model_id in self.models


@dataclass(frozen=True)
class Detection:
    ""

    gpus: tuple[Gpu, ...] = ()
    cpu_count: int | None = None
    ram_gb: float | None = None
    backends: tuple[Backend, ...] = ()
    docker: bool = False
    provenance: Mapping[str, str] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    #
    #
    swept: tuple[ProbeTarget, ...] = ()

    @property
    def has_gpu(self) -> bool:
        return bool(self.gpus)

    @property
    def largest_vram_gb(self) -> float | None:
        ""
        sizing = self.sizing_gpu
        return None if sizing is None else sizing.vram_gb

    @property
    def sizing_gpu(self) -> Gpu | None:
        ""
        sized = [g for g in self.gpus if g.vram_gb is not None]
        return max(sized, key=lambda g: g.vram_gb or 0.0, default=None)

    def backend(self, name: str) -> Backend | None:
        return next((b for b in self.backends if b.name == name), None)

    def models_present(self) -> frozenset[str]:
        ""
        return frozenset(m for b in self.backends for m in b.models)

    @property
    def hosts_answering(self) -> tuple[str, ...]:
        ""
        return tuple(dict.fromkeys(b.host for b in self.backends))

    @property
    def has_remote_backend(self) -> bool:
        ""
        return any(not b.is_local for b in self.backends)


def _run(command: Sequence[str]) -> str | None:
    ""
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
    ""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, http.client.HTTPException, RecursionError):
        return None


def _models_from(payload: Any, api: str) -> tuple[str, ...]:
    ""
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
    return tuple(dict.fromkeys(found))  #


#
#
#
#
#
WINDOW_SOURCES: Mapping[str, tuple[str, tuple[str, ...]]] = {
    "vllm": ("/v1/models", ("data", "max_model_len")),
    "llama-server": ("/props", ("default_generation_settings", "n_ctx")),
    "lmstudio": ("/api/v0/models", ("data", "max_context_length")),
    "tgi": ("/info", ("max_total_tokens",)),
}


def _window_from(payload: Any, keys: tuple[str, ...]) -> int | None:
    ""
    if not keys:
        if isinstance(payload, int) and not isinstance(payload, bool):
            return payload if payload > 0 else None
        return None
    if isinstance(payload, list):
        found = [_window_from(row, keys) for row in payload]
        known = [n for n in found if n is not None]
        return min(known) if known else None
    if not isinstance(payload, dict):
        return None
    return _window_from(payload.get(keys[0]), keys[1:])


def _served_window(
    target: ProbeTarget, listing: Any, timeout: float
) -> tuple[int | None, str]:
    ""
    source = WINDOW_SOURCES.get(target.kind)
    if source is None:
        return None, ""
    path, keys = source
    payload = (
        listing
        if path == "/v1/models"
        else _get_json(target.base_url.rstrip("/") + path, timeout)
    )
    window = _window_from(payload, keys)
    if window is None:
        return None, ""
    return window, f"; serves a {window}-token window (GET {path})"


def probe(target: ProbeTarget, timeout: float = PROBE_TIMEOUT_S) -> Backend | None:
    ""
    path = "/v1/models"
    url = target.base_url.rstrip("/") + path
    payload = _get_json(url, timeout)
    if payload is None:
        return None
    window, read = _served_window(target, payload, timeout)
    return Backend(
        name=target.name,
        base_url=target.base_url,
        api=target.api,
        models=_models_from(payload, target.api),
        how=f"answered GET {path} at {target.base_url} within {timeout:g}s{read}",
        host=target.host,
        kind=target.kind,
        window=window,
    )


def probe_all(
    targets: Sequence[ProbeTarget] = DEFAULT_PROBE_TARGETS,
    timeout: float = PROBE_TIMEOUT_S,
) -> tuple[Backend, ...]:
    ""
    if not targets:
        return ()
    with ThreadPoolExecutor(max_workers=len(targets)) as pool:
        results = pool.map(lambda t: probe(t, timeout), targets)
    return tuple(b for b in results if b is not None)


def _reading() -> Mapping[str, Any]:
    ""
    from mcgyvr.serving import rigscan

    return rigscan.read_machine()


def detect_gpus(
    reading: Mapping[str, Any] | None = None,
) -> tuple[tuple[Gpu, ...], tuple[str, ...]]:
    ""
    reading = _reading() if reading is None else reading
    how = "nvidia-smi, read by mcgyvr.serving.rigscan"
    unread = {
        str(u.get("field")): str(u.get("why"))
        for u in reading.get("unread") or ()
        if isinstance(u, Mapping)
    }
    gpus: list[Gpu] = []
    notes: list[str] = []
    for card in reading.get("cards") or ():
        if card.get("vendor") != "nvidia":
            continue
        key = f"card.nvidia.{card.get('index')}"
        name, total = card.get("name"), card.get("total_mib")
        if not isinstance(name, str):
            notes.append(
                f"{GPU_ROW_NOT_READ}, so that card is missing from the list: "
                f"{_quoted(unread.get(f'{key}.name', 'its name was not read'))}. "
                "Read the card list as incomplete, not short."
            )
            continue
        if not isinstance(total, int):
            gpus.append(Gpu(name=name, vram_gb=None, how=how))
            notes.append(
                f"{GPU_SIZE_UNDETERMINED} for {_quoted(name)}: "
                f"{_quoted(unread.get(f'{key}.total', 'its size was not read'))}. "
                "The card is listed with no size: bind a unit to it by hand, "
                "stating the card room it needs as `room_mib`."
            )
            continue
        gpus.append(Gpu(name=name, vram_gb=round(total / MIB_PER_GB, 1), how=how))
    tool = unread.get("cards.nvidia-smi")
    if tool is not None and (gpus or notes):
        #
        #
        notes.append(
            f"{GPU_ROW_NOT_READ}: {_quoted(tool)}. Read the card list as "
            "incomplete, not short."
        )
    if not gpus and not notes:
        if tool is not None and "printed no card" in tool:
            return (), ("GPU: nvidia-smi ran but reported no device.",)
        return (), (
            "GPU: not determined — nvidia-smi is absent or failed"
            + (f" ({_quoted(tool)})" if tool else "")
            + ". Cards of other vendors are not proposed from; on those "
            "machines bind VRAM by hand rather than trusting a zero here.",
        )
    if not gpus:
        return (), (
            "GPU: nvidia-smi ran but reported no device this could read.",
            *notes,
        )
    return tuple(gpus), tuple(notes)


def detect_ram_gb(reading: Mapping[str, Any] | None = None) -> tuple[float | None, str]:
    ""
    reading = _reading() if reading is None else reading
    memory = reading.get("memory")
    total = memory.get("total_gb") if isinstance(memory, Mapping) else None
    if not isinstance(total, int | float):
        return None, "not determined — the reader read no memory total"
    available = memory.get("available_gb") if isinstance(memory, Mapping) else None
    source = "the kernel's MemTotal" if available is not None else "sysctl hw.memsize"
    return float(total), f"{source}, read by mcgyvr.serving.rigscan"


def detect_docker() -> tuple[bool, str]:
    ""
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
    ""
    reading = _reading()
    gpus, gpu_notes = detect_gpus(reading)
    ram_gb, ram_how = detect_ram_gb(reading)
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
            f"Sandbox: no Docker daemon ({docker_how}), so `sandbox.mode: "
            f"docker` is refused here. `sandbox.mode: tempdir` (or "
            f"`sandbox.allow_fallback: true`) runs tasks in a temp directory, "
            f"the explicitly weaker mode: a contract's acceptance commands run "
            f"without a shell, but each runs whatever program it names, on the "
            f"host."
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
        swept=tuple(targets),
    )
