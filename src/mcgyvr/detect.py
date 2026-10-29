"""Detect what this machine can offer a run: GPU cards and their VRAM,
system RAM, Docker availability, and any inference backend answering on
the well-known local ports.

Every value carries a `how`/provenance string naming where it came from,
and everything that could not be read becomes a note instead of a silent
zero, so a degraded reading is reported as incomplete rather than as
absent.
"""

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

from mcgyvr.scan import Host

# Seconds allowed for one HTTP probe of a candidate backend.
# Seconds allowed for one helper command started by _run.
PROBE_TIMEOUT_S = 1.0
COMMAND_TIMEOUT_S = 5.0

MIB_PER_GB = 1024.0

# Host assumed when none is named: the machine detect itself runs on.
DEFAULT_HOST = "localhost"

# Host spellings that mean "this machine", compared as exact strings:
# the default host plus the loopback literals with and without brackets.
LOCAL_HOSTS = (DEFAULT_HOST, "127.0.0.1", "::1", "[::1]")


def is_local_host(host: str) -> bool:
    """True when host is one of LOCAL_HOSTS, i.e. this machine; the match is
    an exact string comparison, no DNS lookup."""
    return host in LOCAL_HOSTS


def host_system(host: str) -> str:
    """The system `host` is: this machine's (`mcgyvr.hostos.os_name`) for a name
    of this machine, else the one its rig file records, Linux when it records
    none (`mcgyvr.serving.gatelib.rig_system`). No ssh is made."""
    if is_local_host(host):
        from mcgyvr import hostos

        return hostos.os_name()
    from mcgyvr.serving import gatelib

    return gatelib.rig_system(host)


@dataclass(frozen=True)
class ProbeTarget:
    """One candidate backend to ask: a display name, the base URL to call, the
    API dialect it speaks, the host it lives on, and the kind that decides
    which context-window source (WINDOW_SOURCES) applies to it."""

    name: str
    base_url: str
    api: str  # Wire dialect label, copied unchanged into Backend.api.
    host: str = DEFAULT_HOST
    kind: str = ""  # Empty means "same as name"; filled in by __post_init__.

    def __post_init__(self) -> None:
        # A target built without an explicit kind takes its own name as the
        # kind, because WINDOW_SOURCES is keyed by kind; the window lookup
        # therefore still works for callers that only pass a name.
        # The instance is frozen, so the default is written through
        # object.__setattr__ rather than by plain assignment.
        if not self.kind:
            object.__setattr__(self, "kind", self.name)


# The (kind, port, api) triples every default sweep is built from: the
# conventional local port of each well-known server.
# Names here double as kinds for WINDOW_SOURCES lookups, and the order is
# the order targets are probed and reported in.
PORT_CONVENTIONS: tuple[tuple[str, int, str], ...] = (
    ("llama-server", 8080, "openai"),
    ("vllm", 8000, "openai"),
    ("lmstudio", 1234, "openai"),
    ("tgi", 3000, "openai"),
)


def _host_token(host: str) -> str:
    """Turn a host into a short identifier usable inside a target name: runs
    of non-alphanumerics collapse to one underscore, the result is
    lowercased, never starts with a digit, and an empty result becomes
    "host"."""
    token = re.sub(r"[^A-Za-z0-9]+", "_", host).strip("_").lower()
    if not token:
        return "host"
    return token if token[0].isalpha() else f"h{token}"


def targets_for(
    hosts: Sequence[str] = (DEFAULT_HOST,),
    conventions: Sequence[tuple[str, int, str]] = PORT_CONVENTIONS,
) -> tuple[ProbeTarget, ...]:
    """Build one ProbeTarget per (host, convention) pair. Hosts are stripped
    and de-duplicated in first-seen order; when more than one host is
    swept, every target name gets a host token prefix so names stay
    unique."""
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


#: Note prefix for a card nvidia-smi named but whose total memory could
#: not be read: the card is still listed, with no size, and VRAM for it is
#: bound by hand instead.
GPU_SIZE_UNDETERMINED = "GPU: memory size not determined"
#: Note prefix for a printed nvidia-smi row that could not be read as a
#: card, and for the tool itself failing after some rows were still read.
GPU_ROW_NOT_READ = "GPU: nvidia-smi printed a row that could not be read as a card"
#: Longest repr() of a machine-produced string kept whole inside a note,
#: so unexpected output cannot flood the message with a wall of text.
#: Longer strings are shortened in the middle by _quoted, keeping both ends.
ROW_QUOTED_AT_MOST = 200


def _quoted(text: str) -> str:
    """Return repr() of text for use inside a note, with the middle cut out
    of anything longer than ROW_QUOTED_AT_MOST characters."""
    shown = repr(text)
    if len(shown) <= ROW_QUOTED_AT_MOST:
        return shown
    keep = (ROW_QUOTED_AT_MOST - len(" ... ")) // 2
    return f"{shown[:keep]} ... {shown[-keep:]}"


@dataclass(frozen=True)
class Gpu:
    """One NVIDIA card, or a Mac's unified-memory GPU, as rigscan read it: its
    name, its VRAM in GB rounded to one decimal (None when the size could not
    be read), and the `how` string naming the source. A `unified` GPU's VRAM is
    the share of the machine's memory it may take; `figure` says whether the
    size is the card's own `reading` or an `estimate`."""

    name: str
    vram_gb: float | None
    how: str
    unified: bool = False
    figure: str = "reading"

    @property
    def size(self) -> str:
        """Display form of the VRAM: "N GB" without trailing zeros, or a plain
        statement that the size was not determined."""
        if self.vram_gb is None:
            return "memory size not determined"
        return f"{self.vram_gb:g} GB"


@dataclass(frozen=True)
class Backend:
    """A model server that answered a probe: where it lives, its API dialect
    and kind, the model ids it listed, the `how` string recording the request
    that succeeded, and the context window it advertises when the kind is
    known."""

    name: str
    base_url: str
    api: str
    models: tuple[str, ...]
    how: str
    host: str = DEFAULT_HOST
    kind: str = ""  # Left empty to mean "same as name"; filled by __post_init__.
    #: Context window the server advertises for its models, in tokens, as read
    #: from the endpoint that WINDOW_SOURCES lists for this kind.
    #: None when the kind has no known window source, when the extra request
    #: failed, or when the payload carried no usable positive number - so None
    #: means "not learned here", never "unbounded".
    #: Set during probing by _served_window, and left None everywhere else.
    window: int | None = None

    def __post_init__(self) -> None:
        if not self.kind:
            object.__setattr__(self, "kind", self.name)

    @property
    def is_local(self) -> bool:
        """True when this backend's host is one of LOCAL_HOSTS."""
        return is_local_host(self.host)


@dataclass(frozen=True)
class Detection:
    """Everything one detection pass established: what was read, the
    provenance strings saying how each value was obtained, notes describing
    what could not be read, and the targets that were swept."""

    gpus: tuple[Gpu, ...] = ()
    cpu_count: int | None = None
    ram_gb: float | None = None
    backends: tuple[Backend, ...] = ()
    docker: bool = False
    provenance: Mapping[str, str] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    # The targets the sweep actually asked, so a later reader can tell
    # "this machine had nothing" apart from "these hosts were never probed".
    swept: tuple[ProbeTarget, ...] = ()
    #: The system the reading was taken on; None when the reading had none.
    host: Host | None = None

    def backend(self, name: str) -> Backend | None:
        return next((b for b in self.backends if b.name == name), None)

    def models_present(self) -> frozenset[str]:
        """Every model id listed by any backend, de-duplicated into a
        frozenset."""
        return frozenset(m for b in self.backends for m in b.models)

    @property
    def hosts_answering(self) -> tuple[str, ...]:
        """Hosts of the backends that answered, de-duplicated in first-seen
        order."""
        return tuple(dict.fromkeys(b.host for b in self.backends))

    @property
    def has_remote_backend(self) -> bool:
        """True when at least one answering backend is not on this machine."""
        return any(not b.is_local for b in self.backends)


def _run(command: Sequence[str]) -> str | None:
    """Run command and return its stdout, or None when the program is not on
    PATH, when running it raised or timed out, or when it exited non-zero.
    stderr is captured and discarded."""
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
    """GET url and parse the body as JSON, returning None on any failure:
    connection error, HTTP status error, undecodable or over-nested
    body."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, http.client.HTTPException, RecursionError):
        return None


def _models_from(payload: Any, api: str) -> tuple[str, ...]:
    """Pull model ids out of an OpenAI-shaped listing: the "data" rows whose
    "id" is a string, de-duplicated in order. Any other shape yields (). The
    api argument is accepted but not consulted."""
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
    return tuple(dict.fromkeys(found))  # De-duplicate, keeping the server's order.


#: Per-kind recipe for learning the served context window: the path to GET
#: and the key path down into the JSON that path answers with.
#: "/v1/models" reuses the listing the probe already fetched; every other
#: path is a second request made only after a target has answered.
#: The key path drops one element per nesting level and ends at a positive
#: int; a list met on the way is reduced to the smallest value found.
WINDOW_SOURCES: Mapping[str, tuple[str, tuple[str, ...]]] = {
    "vllm": ("/v1/models", ("data", "max_model_len")),
    "llama-server": ("/props", ("default_generation_settings", "n_ctx")),
    "lmstudio": ("/api/v0/models", ("data", "max_context_length")),
    "tgi": ("/info", ("max_total_tokens",)),
}


def _window_from(payload: Any, keys: tuple[str, ...]) -> int | None:
    """Walk keys down into payload and return the context window found. An
    empty key path means payload itself should be the number; a list is
    searched element-wise with the smallest value winning; a missing,
    boolean or non-positive value yields None."""
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
    """Read the advertised context window for target, reusing listing when
    the source path is /v1/models. Returns (window, suffix), where suffix is
    "" when nothing was learned and otherwise a clause naming the window and
    the path it came from, to be appended to the probe's `how` text."""
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
    """Ask one target for its model list on /v1/models and describe it as a
    Backend. Returns None when the request failed or its body did not parse
    as JSON (a literal null included); an empty model list still counts as
    answering."""
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
    """Probe every target concurrently, one worker per target, and return the
    backends that answered in target order, dropping the ones that did
    not."""
    if not targets:
        return ()
    with ThreadPoolExecutor(max_workers=len(targets)) as pool:
        results = pool.map(lambda t: probe(t, timeout), targets)
    return tuple(b for b in results if b is not None)


def _reading() -> Mapping[str, Any]:
    """Return rigscan.read_machine(), the card and memory reading detection is
    built on; mcgyvr.serving.rigscan is imported inside the call rather than
    at module import."""
    from mcgyvr.serving import rigscan

    return rigscan.read_machine()


def detect_gpus(
    reading: Mapping[str, Any] | None = None,
) -> tuple[tuple[Gpu, ...], tuple[str, ...]]:
    """Turn a rigscan reading into Gpu entries, keeping NVIDIA cards and a Mac's
    unified-memory GPU. A
    card with a readable name is kept even when its size is missing (vram_gb
    None); a row that could not be read as a card is dropped and noted.
    Returns (gpus, notes): the notes flag the list as incomplete rather than
    short, and when no card is read at all they say why instead."""
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
        if card.get("kind") == "unified":
            gpus.extend(_unified_gpu(card))
            continue
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
        # The tool itself failed or printed something unreadable, yet some
        # rows were still read: keep those cards and flag the list as incomplete.
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


def _unified_gpu(card: Mapping[str, Any]) -> tuple[Gpu, ...]:
    """A Mac's unified-memory GPU as one Gpu, sized by the share of memory it may
    take, or nothing when it has no name to list it by."""
    name, total = card.get("name"), card.get("total_mib")
    if not isinstance(name, str):
        return ()
    how = f"{card.get('how') or 'unified memory'}, read by mcgyvr.serving.rigscan"
    size = round(total / MIB_PER_GB, 1) if isinstance(total, int) else None
    figure = str(card.get("figure") or "reading")
    return (Gpu(name=name, vram_gb=size, how=how, unified=True, figure=figure),)


def detect_ram_gb(reading: Mapping[str, Any] | None = None) -> tuple[float | None, str]:
    """Total system RAM in GB from a rigscan reading, plus the `how` string
    naming the source; (None, reason) when the reading carried no total."""
    reading = _reading() if reading is None else reading
    memory = reading.get("memory")
    total = memory.get("total_gb") if isinstance(memory, Mapping) else None
    if not isinstance(total, int | float):
        return None, "not determined — the reader read no memory total"
    host = reading.get("host")
    system = host.get("os") if isinstance(host, Mapping) else None
    source = {
        "darwin": "sysctl hw.memsize",
        "windows": "Windows' CIM memory figures",
    }.get(str(system), "the kernel's MemTotal")
    return float(total), f"{source}, read by mcgyvr.serving.rigscan"


def detect_docker() -> tuple[bool, str]:
    """Decide whether a usable Docker daemon is available: refuse when a
    foreign daemon is configured, otherwise require docker on PATH and a
    `docker info` that prints a server version. Returns (available, how),
    where how explains the verdict either way."""
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
    """Run one full pass: read the machine once, derive GPUs, RAM and Docker
    from it, probe every target concurrently, and record os.cpu_count().
    Everything unresolved becomes a note (no backend answered, no Docker for
    the docker sandbox, no CPU count), and each value obtained gets a
    provenance entry."""
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
        host=Host.from_reading(reading.get("host")),
    )
