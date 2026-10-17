""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcgyvr import derived
from mcgyvr.config import ROLE_SLEEPER, Config
from mcgyvr.propose import DEFAULT_HEADROOM_GB
from mcgyvr.scan import Gpu, Scan, default_weights_dir
from mcgyvr.serving import vramfit

#
#
#
DEFAULT_ENGINE = "llama.cpp"

#
#
#
KNOWN_ENGINES = ("llama.cpp", "vllm", "diffusers", "tts", "comfyui")

#
#ll
#at
#
MEDIA_ENGINES = ("diffusers", "tts", "comfyui")

#
#
#
#
MEDIA_ENGINES_NOT_WIRED: tuple[str, ...] = ()

#
#
#
#
#
#
#
#

#
#
#
#
DEFAULT_UBATCH = 512

#id
#
#
#
DEFAULT_PORT = 8080

#
#
#
#
#
COMPOSE_PREFIX = "compose."
COMPOSE_SUFFIX = ".yml"
#
#
#
#
SLEEPER_PROFILE = "asleep"

#
#
#
#
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

#t,
# a
#
#
#
#
#
#
#
#
#
#

#
#
#
#
#
#
#

#
#
#
#
#
#
#
#
MODE_RAM_HEADROOM_GB = 0.5

#
#
#
#
#
#
#
#
#
REFUSAL_RAM_HEADROOM_GB = 2.0

#
MAX_WIDTH = 32
#
#
#
#
#
#
#
#un
#ry
#
VLLM_DEFAULT_SEQS = 8
#
#
HF_CACHE_MOUNT = "/root/.cache/huggingface"

#
#
#
#t.
SIZE_TOLERANCE_GB = 0.005

#
#
#
#
#
#
#
#
SPECULATIVE_NONE = "none"
SPECULATIVE_MTP = "mtp"
SPECULATIVE_CHOICES = (SPECULATIVE_NONE, SPECULATIVE_MTP)
#
#
DEFAULT_SPEC_DRAFT_N_MAX = 2

_BYTES_PER_GIB = 1024**3

#
#
#
ROLE_SERVE = "serve"
ROLE_RPC = "rpc"
ROLE_HEADLESS = "headless"
ROLES = (ROLE_SERVE, ROLE_RPC, ROLE_HEADLESS)

#
#
SHARDS_KEY = "shards"
#
#
#
RPC_DEFAULT_PORT = 50052
#
#
#
VLLM_MASTER_PORT = 29501


class UnitError(Exception):
    ""


@dataclass(frozen=True)
class ModelSpec:
    ""

    name: str
    vram_gb: float
    ram_gb: float
    disk_gb: float
    vae_decode_gb: float = 0.0
    cpu_only: bool = False
    moe: bool = False
    geometry: Mapping[str, Any] | None = field(default=None, compare=False)
    hf_cache: str = ""
    serve_args: tuple[str, ...] = ()
    kv_cache_dtype_k: str | None = None
    kv_cache_dtype_v: str | None = None
    speculative: str = SPECULATIVE_NONE
    spec_draft_n_max: int = DEFAULT_SPEC_DRAFT_N_MAX

    def __post_init__(self) -> None:
        if self.speculative not in SPECULATIVE_CHOICES:
            raise UnitError(
                f"{self.name}: units.<unit>.launch.speculative is "
                f"{self.speculative!r}, which this build does not know. Valid: "
                f"{', '.join(SPECULATIVE_CHOICES)} -- `mtp` is llama.cpp's "
                f"--spec-type draft-mtp, the GGUF's own grafted head as the draft"
            )
        if (
            isinstance(self.spec_draft_n_max, bool)
            or not isinstance(self.spec_draft_n_max, int)
            or self.spec_draft_n_max < 1
        ):
            raise UnitError(
                f"{self.name}: units.<unit>.launch.spec_draft_n_max is "
                f"{self.spec_draft_n_max!r}; --spec-draft-n-max is how many "
                f"tokens the head drafts per step and must be at least 1 "
                f"(the default is {DEFAULT_SPEC_DRAFT_N_MAX})"
            )
        if self.geometry is None:
            return
        scanned = Path(str(self.geometry.get("file") or "")).name
        wanted = _weights_file_name(self.name)
        if scanned != wanted:
            raise UnitError(
                f"{self.name}: its geometry was scanned from {scanned!r} and this "
                f"model serves {wanted!r}. A scan describes one file and this is "
                f"not it; re-scan: python -m mcgyvr.serving.ggufscan <gguf>"
            )
        size_bytes = self.geometry.get("size_bytes")
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool):
            raise UnitError(
                f"{self.name}: its geometry states no size_bytes, so it is not a "
                f"ggufscan row; re-scan: python -m mcgyvr.serving.ggufscan <gguf>"
            )
        measured = size_bytes / _BYTES_PER_GIB
        if self.disk_gb and abs(self.disk_gb - measured) > SIZE_TOLERANCE_GB:
            raise UnitError(
                f"{self.name}: disk_gb says {self.disk_gb!r} GiB and the geometry "
                f"says {measured:.3f} GiB ({size_bytes} bytes). Each deviation "
                f"from a scan requires a new scan: drop disk_gb, or re-scan: "
                f"python -m mcgyvr.serving.ggufscan <gguf>"
            )
        object.__setattr__(self, "disk_gb", measured)
        object.__setattr__(self, "moe", bool(self.geometry.get("placeable_blocks")))


@dataclass(frozen=True)
class Width:
    ""

    value: int
    how: str


#
#
#
#
#
HOST_FIGURE_NOT_READ = (
    "vLLM host memory beyond the weights: not read on this machine; "
    "none is charged for it"
)

#
#
HOST_FIGURE_SETTING_NOT_USED = "your setting in {where} is not used by the sizing"

#
#
HOST_FIGURE_SETTING_UNKNOWN = "whether your own numbers set it is not known: {why}"


@dataclass(frozen=True)
class Fit:
    ""

    fits: bool
    headroom_gb: float
    why: str
    #re
    #
    #
    #
    vram_gb: float = 0.0
    #
    #
    #
    #
    #
    #
    #
    #
    #me
    #
    ram_gb: float = 0.0
    #
    #
    #
    #
    #
    load_mode: str | None = None
    #
    #
    #
    #ut
    #
    #
    #.
    #
    #
    #
    #
    #
    #
    card_free_gb: float = 0.0
    #
    #
    #
    #
    #
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class UnitKey:
    ""

    host: str
    model: str
    engine: str
    port: int = DEFAULT_PORT

    @property
    def slug(self) -> str:
        return f"{self.host}:{self.port}/{self.model}/{self.engine}"


@dataclass(frozen=True)
class Unit:
    ""

    key: UnitKey
    host: str
    model: str
    engine: str
    gpu: int
    weights: Path
    width: Width
    args: Mapping[str, str]
    fit: Fit
    port: int = DEFAULT_PORT
    rungs: tuple[str, ...] = ()
    #
    #
    #
    #
    image: str | None = None
    extra: tuple[str, ...] = ()
    # a
    #
    #
    cpu_only: bool = False
    #
    #
    #
    #
    resident_claim_gb: float = 0.0
    #
    #
    #
    #
    gpus: tuple[int, ...] = ()
    #
    #
    #
    #
    role: str = ROLE_SERVE
    #
    #
    env: Mapping[str, str] = field(default_factory=dict)
    #
    #
    #
    #
    asleep: bool = False

    @property
    def cards(self) -> tuple[int, ...]:
        ""
        return self.gpus or (self.gpu,)

    @property
    def weights_dir(self) -> Path:
        ""
        if self.engine == "vllm" or self.engine in MEDIA_ENGINES:
            return self.weights
        return self.weights.parent


def fit(
    scan: Scan,
    spec: ModelSpec,
    *,
    engine: str,
    width: int | None = None,
    ctx_per_slot: int,
) -> Fit:
    ""
    if engine not in KNOWN_ENGINES:
        return Fit(
            fits=False,
            headroom_gb=DEFAULT_HEADROOM_GB,
            why=_engine_not_wired(spec.name, engine),
        )
    if engine in MEDIA_ENGINES:
        return _sized_media(scan, spec, engine=engine)
    sized = _sized(scan, spec, engine=engine, width=width, ctx_per_slot=ctx_per_slot)
    notes = _host_figure_notes(engine)
    if not notes:
        return sized
    said = sized.why if sized.why.endswith(".") else f"{sized.why}."
    return replace(sized, notes=notes, why=" ".join((said, *notes)))


def _host_figure_notes(engine: str) -> tuple[str, ...]:
    ""
    if engine not in derived.RUNTIME_RESIDENT_READ:
        return ()
    try:
        where = derived.user_setting(derived.RUNTIME_RESIDENT, engine)
    except (derived.DerivedNumbersError, RuntimeError) as exc:
        unknown = HOST_FIGURE_SETTING_UNKNOWN.format(why=exc)
        return (f"{HOST_FIGURE_NOT_READ}; {unknown}",)
    if where is None:
        return (HOST_FIGURE_NOT_READ,)
    unused = HOST_FIGURE_SETTING_NOT_USED.format(where=where)
    return (f"{HOST_FIGURE_NOT_READ}; {unused}",)


def _sized(
    scan: Scan,
    spec: ModelSpec,
    *,
    engine: str,
    width: int | None,
    ctx_per_slot: int,
) -> Fit:
    ""
    free_bytes = _free_vram_bytes(scan)
    free_vram = free_bytes / _BYTES_PER_GIB
    available_ram = scan.memory.available_gb if scan.memory else 0.0

    if spec.speculative == SPECULATIVE_MTP and not _mtp_head_blocks(spec):
        return Fit(fits=False, headroom_gb=DEFAULT_HEADROOM_GB, why=_no_mtp_head(spec))
    if spec.moe and spec.geometry is None:
        return Fit(
            fits=False, headroom_gb=DEFAULT_HEADROOM_GB, why=_needs_geometry(spec)
        )
    if scan.disk is not None and spec.disk_gb > scan.disk.free_gb:
        return Fit(
            fits=False,
            headroom_gb=DEFAULT_HEADROOM_GB,
            why=(
                f"{spec.name}: needs {spec.disk_gb:.1f} GB of disk, "
                f"{scan.disk.free_gb:.1f} GB free at {scan.disk.path}"
            ),
        )

    try:
        placed = _placement(
            spec,
            free_bytes,
            width,
            engine=engine,
            host=scan.machine.host,
            ctx_per_slot=ctx_per_slot,
        )
    except UnitError as exc:
        return Fit(fits=False, headroom_gb=_allowance_gb(spec), why=str(exc))
    #
    #'s
    #so
    #
    #
    #
    #ob
    #
    #t.
    #
    #
    #
    #
    #
    #
    #
    #
    #
    #
    load_mode: str | None = None
    if placed.ram_gb and spec.disk_gb + MODE_RAM_HEADROOM_GB > available_ram:
        if placed.ram_gb + REFUSAL_RAM_HEADROOM_GB > available_ram:
            return Fit(
                fits=False,
                headroom_gb=DEFAULT_HEADROOM_GB,
                why=(
                    f"{spec.name}: needs {placed.ram_gb:.1f} GB of RAM for "
                    f"the experts it spills{_offload_note(spec, placed)} with "
                    f"{REFUSAL_RAM_HEADROOM_GB:.1f} GB held back, or "
                    f"{spec.disk_gb:.1f} GB to hold its blob mapped with "
                    f"{MODE_RAM_HEADROOM_GB:.1f} GB held back, against "
                    f"{available_ram:.1f} GB available. No loading mode "
                    f"fits this host"
                ),
            )
        load_mode = "none"
    if spec.geometry is None and placed.vram_gb + DEFAULT_HEADROOM_GB > free_vram:
        return Fit(
            fits=False,
            headroom_gb=DEFAULT_HEADROOM_GB,
            why=(
                f"{spec.name}: needs {placed.vram_gb:.1f} GB on the card plus "
                f"{DEFAULT_HEADROOM_GB:.1f} GB headroom, "
                f"{free_vram:.1f} GB free"
            ),
        )

    if spec.geometry is None:
        held = f"{DEFAULT_HEADROOM_GB:.1f} GB headroom held back"
    else:
        held = (
            f"{placed.width} slot(s) at {ctx_per_slot} context each, "
            f"{placed.headroom_gb:.2f} GB of it scratch allowance"
        )
    spilled = (
        f", {placed.ram_gb:.1f} GB of experts in RAM{_offload_note(spec, placed)}"
        if spec.moe and placed.ram_gb
        else ""
    )
    head = (
        f", {placed.head_bytes >> 20} MiB of MTP head on the card"
        if placed.head_bytes
        else ""
    )
    unmapped = (
        f", read with --load-mode none because its {spec.disk_gb:.1f} GB blob "
        f"does not fit {available_ram:.1f} GB of RAM mapped"
        if load_mode
        else ""
    )
    #
    #
    #
    #
    if not placed.ram_gb:
        wants_ram = 0.0
    elif load_mode == "none":
        wants_ram = placed.ram_gb
    else:
        wants_ram = spec.disk_gb
    return Fit(
        fits=True,
        vram_gb=placed.vram_gb,
        ram_gb=wants_ram,
        headroom_gb=placed.headroom_gb,
        load_mode=load_mode,
        card_free_gb=free_vram,
        why=(
            f"{spec.name}: {placed.vram_gb:.1f} GB on the card of "
            f"{free_vram:.1f} GB free, {held}{head}{spilled}{unmapped}"
        ),
    )


def _sized_media(scan: Scan, spec: ModelSpec, *, engine: str) -> Fit:
    ""
    free_vram = _free_vram_bytes(scan) / _BYTES_PER_GIB
    available_ram = scan.memory.available_gb if scan.memory else 0.0
    if scan.disk is not None and spec.disk_gb > scan.disk.free_gb:
        return Fit(
            fits=False,
            headroom_gb=DEFAULT_HEADROOM_GB,
            why=(
                f"{spec.name}: needs {spec.disk_gb:.1f} GB of disk, "
                f"{scan.disk.free_gb:.1f} GB free at {scan.disk.path}"
            ),
        )
    spike = spec.vae_decode_gb if engine == "diffusers" else 0.0
    peak = 0.0 if spec.cpu_only else spec.vram_gb + spike
    if not spec.cpu_only and peak + DEFAULT_HEADROOM_GB > free_vram:
        return Fit(
            fits=False,
            headroom_gb=DEFAULT_HEADROOM_GB,
            why=(
                f"{spec.name}: needs {peak:.1f} GB on the card plus "
                f"{DEFAULT_HEADROOM_GB:.1f} GB headroom, "
                f"{free_vram:.1f} GB free"
            ),
        )
    if spec.ram_gb > available_ram:
        return Fit(
            fits=False,
            headroom_gb=DEFAULT_HEADROOM_GB,
            why=(
                f"{spec.name}: needs {spec.ram_gb:.1f} GB of RAM for the "
                f"offloaded components, against {available_ram:.1f} GB available"
            ),
        )
    ram_clause = f", {spec.ram_gb:.1f} GB in RAM" if spec.ram_gb else ""
    if spec.cpu_only:
        card_clause = "runs on the CPU"
    else:
        card_clause = f"{peak:.1f} GB on the card of {free_vram:.1f} GB free"
    return Fit(
        fits=True,
        vram_gb=peak,
        ram_gb=spec.ram_gb,
        headroom_gb=0.0 if spec.cpu_only else DEFAULT_HEADROOM_GB,
        card_free_gb=0.0 if spec.cpu_only else free_vram,
        why=(f"{spec.name}: {card_clause}{ram_clause}"),
    )


def _require_cache_types(engine: str, spec: ModelSpec) -> tuple[str, str]:
    ""
    kv_k = spec.kv_cache_dtype_k
    kv_v = spec.kv_cache_dtype_v
    if engine == "vllm":
        if kv_k is None:
            raise UnitError(
                f"{spec.name}: served by vLLM, which sizes its KV cache from "
                f"the dtype the model declares, and nothing states one — set "
                f"units.<unit>.launch.kv_cache_dtype_k (`--kv-cache-dtype`) on "
                f"the unit that serves it"
            )
        return kv_k, ""
    missing: list[str] = []
    if kv_k is None:
        missing.append("kv_cache_dtype_k (`-ctk`/`cache_type_k`)")
    if kv_v is None:
        missing.append("kv_cache_dtype_v (`-ctv`/`cache_type_v`)")
    if missing:
        raise UnitError(
            f"{spec.name}: served by llama.cpp, which sizes its cache from "
            f"the K and V dtypes the model declares, and nothing states "
            f"{' and '.join(missing)} — set them under units.<unit>.launch on "
            f"the unit that serves it"
        )
    assert kv_k is not None and kv_v is not None
    return kv_k, kv_v


def _engine_not_wired(name: str, engine: str) -> str:
    ""
    return (
        f"{name}: engine {engine!r} is not wired in this build; mcgyvr will not "
        "size or render a unit for an engine it has no law or launch spec for "
        "rather than apply a text engine's law or invent a number nobody measured."
    )


def unit_for(
    scan: Scan,
    spec: ModelSpec,
    *,
    engine: str = DEFAULT_ENGINE,
    width: int | None = None,
    port: int = DEFAULT_PORT,
    ctx_per_slot: int,
) -> Unit:
    ""
    if engine not in KNOWN_ENGINES:
        raise UnitError(_engine_not_wired(spec.name, engine))
    if engine in MEDIA_ENGINES:
        if not spec.hf_cache:
            raise UnitError(
                f"{spec.name}: served by {engine}, which loads its weights from "
                f"the rig's weights directory, and nothing says where it is — "
                f"set units.<unit>.hf_cache to its absolute path on the rig"
            )
        sized = fit(scan, spec, engine=engine, width=1, ctx_per_slot=ctx_per_slot)
        if not sized.fits:
            raise UnitError(f"{scan.machine.host}: {sized.why}")
        weights = Path(spec.hf_cache)
        gpu_index = -1 if spec.cpu_only else _roomiest_gpu(scan).index
        return Unit(
            key=UnitKey(
                host=scan.machine.host, model=spec.name, engine=engine, port=port
            ),
            host=scan.machine.host,
            model=spec.name,
            engine=engine,
            gpu=gpu_index,
            weights=weights,
            width=Width(value=1, how="default"),
            args={"--model": str(weights)},
            fit=sized,
            port=port,
            rungs=(),
            extra=spec.serve_args,
            cpu_only=spec.cpu_only,
        )
    cache_type_k, cache_type_v = _require_cache_types(engine, spec)
    if engine == "vllm" and spec.speculative != SPECULATIVE_NONE:
        raise UnitError(
            f"{spec.name}: units.<unit>.launch.speculative is "
            f"{spec.speculative!r}, and this unit is served by vLLM. That key is "
            f"llama.cpp's --spec-type draft-mtp, the GGUF's own grafted head "
            f"run as the draft; vLLM's speculative decoding is "
            f"--speculative-config, a different mechanism with its own knobs "
            f"that this key does not express. Set it to none here, or serve "
            f"the model under llama.cpp"
        )
    if engine == "vllm" and not spec.hf_cache:
        raise UnitError(
            f"{spec.name}: served by vLLM, which loads a repository id from the "
            f"rig's HuggingFace cache, and nothing says where that cache is — "
            f"set units.<unit>.hf_cache to its absolute path on the rig"
        )
    sized = fit(scan, spec, engine=engine, width=width, ctx_per_slot=ctx_per_slot)
    if not sized.fits:
        raise UnitError(f"{scan.machine.host}: {sized.why}")

    gpu = _roomiest_gpu(scan)
    if engine == "vllm":
        #
        #
        #
        if width is not None:
            seqs = Width(value=width, how="written")
        else:
            seqs = Width(value=VLLM_DEFAULT_SEQS, how="default")
        host = scan.machine.host
        return Unit(
            key=UnitKey(host=host, model=spec.name, engine=engine, port=port),
            host=host,
            model=spec.name,
            engine=engine,
            gpu=gpu.index,
            weights=Path(spec.hf_cache),
            width=seqs,
            args={
                "--max-num-seqs": str(seqs.value),
                "--max-model-len": str(ctx_per_slot),
                "--kv-cache-dtype": cache_type_k,
            },
            fit=sized,
            port=port,
            rungs=(),
            extra=spec.serve_args,
        )
    #
    #
    #
    placed = _placement(
        spec,
        gpu.vram.free_mib << 20,
        width,
        engine=engine,
        host=scan.machine.host,
        ctx_per_slot=ctx_per_slot,
    )
    if width is not None:
        chosen = Width(value=width, how="written")
    elif spec.geometry is not None:
        chosen = Width(value=placed.width, how="derived")
    else:
        chosen = Width(value=placed.width, how="default")
    weights = _weights_path(scan, spec)

    #ch
    #
    #
    #
    #
    #
    args: dict[str, str] = {
        "--model": str(weights),
        "-ngl": "99",
        "-c": str(ctx_per_slot * chosen.value),
        "-ub": str(DEFAULT_UBATCH),
        "-b": str(DEFAULT_UBATCH),
        "-fa": "on",
        "--parallel": str(chosen.value),
        "-t": str(_threads(scan)),
        "-ctk": cache_type_k,
        "-ctv": cache_type_v,
    }
    #
    #
    #
    #
    if placed.n_cpu_moe > 0:
        args["--n-cpu-moe"] = str(placed.n_cpu_moe)
    #
    #
    #
    #
    if spec.speculative == SPECULATIVE_MTP:
        args["--spec-type"] = "draft-mtp"
        args["--spec-draft-n-max"] = str(spec.spec_draft_n_max)
    #
    #
    #
    #
    #
    if sized.load_mode is not None:
        args["--load-mode"] = sized.load_mode

    return Unit(
        key=UnitKey(host=scan.machine.host, model=spec.name, engine=engine, port=port),
        host=scan.machine.host,
        model=spec.name,
        engine=engine,
        gpu=gpu.index,
        weights=weights,
        width=chosen,
        args=args,
        fit=sized,
        port=port,
        rungs=(),
        extra=spec.serve_args,
    )


def units_for(
    config: Config,
    scans: Mapping[str, Scan],
    *,
    specs: Iterable[ModelSpec],
    ctx_per_slot: int | None,
) -> tuple[Unit, ...]:
    ""
    if ctx_per_slot is not None and ctx_per_slot < 1:
        raise UnitError(
            f"the declared context window is {ctx_per_slot}, which is not a "
            f"window: a slot serves at least one token"
        )
    #
    #
    #
    catalogue = {spec.name: spec for spec in specs} | declared_models(config)
    grouped: dict[UnitKey, list[str]] = {}
    hosts: dict[UnitKey, Scan] = {}
    models: dict[UnitKey, ModelSpec] = {}
    widths: dict[UnitKey, int] = {}
    images: dict[UnitKey, str | None] = {}
    #
    #
    #
    windows: dict[UnitKey, dict[int, list[str]]] = {}
    #
    splits: dict[UnitKey, dict[str, Any]] = {}
    #
    roles: dict[UnitKey, dict[str, list[str]]] = {}

    users = config.get("users", 1)
    #
    #
    #
    provision = config.provisions_local_orchestrator

    def _local(name: str | None) -> bool:
        unit = config.units.get(name) if name else None
        return unit is not None and not unit.requires_credential

    #
    #
    #
    #
    served = list(config.ladder.names)
    orchestrator_name = config.get("orchestrator.unit")
    if (
        provision
        and orchestrator_name
        and _local(orchestrator_name)
        and orchestrator_name not in served
    ):
        served.append(orchestrator_name)
    role_extra: list[str] = []
    verifier_name = (
        config.get("verifier.unit") if config.get("verifier.enabled") else None
    )
    if verifier_name and _local(verifier_name) and verifier_name not in served:
        role_extra.append(verifier_name)
    jev_name = config.get("jev.unit")
    if (
        jev_name
        and _local(jev_name)
        and jev_name not in served
        and jev_name not in role_extra
    ):
        role_extra.append(jev_name)

    orchestrator_key: UnitKey | None = None
    for name in (*served, *role_extra):
        unit = config.units.get(name)
        if unit is None:
            raise UnitError(f"{name}: no unit named {name!r}")
        host = host_of(unit.address)
        scan = scans.get(host)
        if scan is None:
            raise UnitError(
                f"{name}: host {host!r} is unscanned — "
                f"run `mcgyvr scan` on {host} before emitting a unit for it"
            )
        spec = catalogue.get(unit.model)
        if spec is None:
            raise UnitError(
                f"{name}: no model spec for {unit.model!r} — it is not in "
                f"the shipped capability table or model catalog, and nothing "
                f"declares it under `launch` in fleet.yaml. Sizing a unit "
                f"needs what the model costs, and mcgyvr will not invent "
                f"that; state it and this model is served on your numbers"
            )

        key = UnitKey(
            host=host,
            model=spec.name,
            #
            #
            engine=unit.engine or DEFAULT_ENGINE,
            port=port_of(unit.address),
        )
        if provision and name == orchestrator_name:
            orchestrator_key = key
        grouped.setdefault(key, []).append(name)
        roles.setdefault(key, {}).setdefault(unit.role, []).append(name)
        if unit.window is not None:
            windows.setdefault(key, {}).setdefault(unit.window, []).append(name)
        hosts.setdefault(key, scan)
        models.setdefault(key, spec)
        images.setdefault(key, unit.image)
        if unit.width is not None:
            #
            #
            widths[key] = max(widths.get(key, 0), unit.width)
        elif provision and name == orchestrator_name and _local(orchestrator_name):
            #
            #
            widths[key] = max(widths.get(key, 0), users)
        if SHARDS_KEY in unit.launch:
            #
            #
            stated = dict(unit.launch)
            first = splits.setdefault(key, stated)
            if first != stated:
                raise UnitError(
                    f"{name}: names the process {key.slug}, which another unit "
                    f"declares with a different launch; one process is split "
                    f"one way"
                )

    def _sized(
        key: UnitKey,
        rungs: list[str],
        scan: Scan,
        reduced: Mapping[str, Scan],
    ) -> list[Unit]:
        ""
        window = _window_for(key, windows.get(key, {}), ctx_per_slot)
        if key in splits:
            head, *workers = _sharded_units(
                config,
                reduced,
                models[key],
                key=key,
                launch=splits[key],
                width=widths.get(key),
                ctx_per_slot=window,
            )
            return [
                replace(head, rungs=tuple(rungs), image=images[key]),
                *(replace(worker, image=images[key]) for worker in workers),
            ]
        return [
            replace(
                _with_rungs(
                    unit_for(
                        scan,
                        models[key],
                        engine=key.engine,
                        width=widths.get(key),
                        port=key.port,
                        ctx_per_slot=window,
                    ),
                    tuple(rungs),
                ),
                image=images[key],
            )
        ]

    asleep = {
        key: _starts_asleep(key, stated, key in splits) for key, stated in roles.items()
    }

    #
    #
    #
    ordered = list(grouped.items())
    ordered.sort(key=lambda pair: pair[0] != orchestrator_key)
    built: list[Unit] = []
    claimed: dict[str, float] = {}
    reduced = dict(scans)
    for key, rungs in ordered:
        scan = hosts[key]
        if key.host in claimed:
            scan = _remaining_scan(scan, claimed[key.host])
            reduced[key.host] = scan
        sized = _sized(key, rungs, scan, reduced)
        if asleep[key]:
            sized[0] = replace(sized[0], asleep=True)
        if key == orchestrator_key:
            claimed[key.host] = sized[0].fit.vram_gb
            sized[0] = replace(sized[0], resident_claim_gb=sized[0].fit.vram_gb)
        built.extend(sized)
    return tuple(built)


def _starts_asleep(key: UnitKey, stated: Mapping[str, list[str]], split: bool) -> bool:
    ""
    if len(stated) > 1:
        said = "; ".join(
            f"{role} ({', '.join(names)})" for role, names in sorted(stated.items())
        )
        raise UnitError(
            f"{key.slug} is one process and its units state two roles: {said}"
        )
    if ROLE_SLEEPER not in stated:
        return False
    names = ", ".join(stated[ROLE_SLEEPER])
    if key.engine != DEFAULT_ENGINE:
        raise UnitError(
            f"{names}: role {ROLE_SLEEPER} is for llama.cpp units, whose sleep is "
            f"a stop of their container; a {key.engine} unit is not started "
            "asleep (vLLM sleeps at level 2 with its process kept)"
        )
    if split:
        raise UnitError(
            f"{names}: role {ROLE_SLEEPER} is for a unit on one card; a unit "
            "split across cards is several processes and is not started asleep"
        )
    return True


def _sharded_units(
    config: Config,
    scans: Mapping[str, Scan],
    spec: ModelSpec,
    *,
    key: UnitKey,
    launch: Mapping[str, Any],
    width: int | None,
    ctx_per_slot: int,
) -> tuple[Unit, ...]:
    ""
    from mcgyvr.serving import sharding, shardlaunch

    engine = key.engine
    cache_type_k, cache_type_v = _require_cache_types(engine, spec)
    if spec.speculative != SPECULATIVE_NONE:
        raise UnitError(
            f"{spec.name}: declares speculative {spec.speculative!r} and a split "
            f"across cards; a split is sized with every block on its cards and "
            f"no draft head, so the two are not combined"
        )
    targets = _shard_targets(spec.name, launch.get(SHARDS_KEY), scans)
    if targets[0].host.lower() != key.host.lower():
        raise UnitError(
            f"{spec.name}: its first shard is on {targets[0].host} and its address "
            f"is on {key.host}; the first card a unit names is one of the machine "
            f"its address points at, where the serving process runs"
        )
    head_scan = scans[key.host]
    if engine == "vllm":
        if not spec.hf_cache:
            raise UnitError(
                f"{spec.name}: served by vLLM, which loads a repository id from "
                f"the rig's HuggingFace cache, and nothing says where that cache "
                f"is — set units.<unit>.hf_cache to its absolute path on the rig"
            )
        table = _tensor_table(config, spec.name, launch.get("tensor_table_json"))
        weights = Path(spec.hf_cache)
        slots = Width(value=width or VLLM_DEFAULT_SEQS, how=_how(width))
    else:
        if spec.geometry is None:
            raise UnitError(_needs_geometry(spec))
        table = spec.geometry
        weights = _weights_path(head_scan, spec)
        slots = Width(value=width or 1, how=_how(width))
    if head_scan.disk is not None and spec.disk_gb > head_scan.disk.free_gb:
        raise UnitError(
            f"{spec.name}: needs {spec.disk_gb:.1f} GB of disk, "
            f"{head_scan.disk.free_gb:.1f} GB free at {head_scan.disk.path}"
        )
    try:
        plan = sharding.choose(
            table,
            targets,
            engine=engine,
            slots=slots.value,
            ctx_per_slot=ctx_per_slot,
            cache_type_k=cache_type_k,
            cache_type_v=cache_type_v,
            n_ubatch=DEFAULT_UBATCH,
            name=spec.name,
            split=_stated_text(spec.name, launch, "split"),
            tensor=_stated_count(spec.name, launch, "tensor_parallel"),
            pipeline=_stated_count(spec.name, launch, "pipeline_parallel"),
        )
        launched = shardlaunch.processes(
            plan,
            model=spec.name,
            weights=weights,
            port=key.port,
            cache_type_k=cache_type_k,
            cache_type_v=cache_type_v,
            threads=_threads(head_scan),
            n_ubatch=DEFAULT_UBATCH,
            rpc_port=_stated_count(spec.name, launch, "rpc_port") or RPC_DEFAULT_PORT,
            master_port=_stated_count(spec.name, launch, "master_port")
            or VLLM_MASTER_PORT,
        )
    except (sharding.ShardingError, shardlaunch.LaunchError) as exc:
        raise UnitError(str(exc)) from exc
    notes = _host_figure_notes(engine)
    allowance = plan.shards[0].allowance_bytes / _BYTES_PER_GIB
    units: list[Unit] = []
    for process in launched:
        held = process.shards
        said = f"{spec.name}: split across cards, {plan.says()}"
        units.append(
            Unit(
                key=UnitKey(
                    host=process.host, model=spec.name, engine=engine, port=process.port
                ),
                host=process.host,
                model=spec.name,
                engine=engine,
                gpu=process.gpus[0],
                weights=weights,
                width=slots,
                args=process.args,
                fit=Fit(
                    fits=True,
                    headroom_gb=allowance,
                    why=" ".join((said, *notes)),
                    vram_gb=max(s.required_bytes for s in held) / _BYTES_PER_GIB,
                    card_free_gb=min(s.target.free_bytes for s in held)
                    / _BYTES_PER_GIB,
                    notes=notes,
                ),
                port=process.port,
                rungs=(),
                extra=(
                    (*process.extra, *spec.serve_args)
                    if process.role != ROLE_RPC
                    else process.extra
                ),
                gpus=process.gpus,
                role=process.role,
                env=dict(process.env),
            )
        )
    return tuple(units)


def _how(width: int | None) -> str:
    return "written" if width is not None else "default"


def _shard_targets(name: str, declared: object, scans: Mapping[str, Scan]) -> list[Any]:
    ""
    from mcgyvr.fleet.spans import SpanError, parse_shard
    from mcgyvr.serving.sharding import Target

    if not isinstance(declared, list) or not declared:
        raise UnitError(
            f"{name}: launch.{SHARDS_KEY} is {declared!r}; it is a list of the "
            f"cards the unit is split across, each `{{rig: <host>, gpu: <index>}}`, "
            f"the first on the machine the unit's address points at"
        )
    targets = []
    for index, entry in enumerate(declared):
        where = f"{name}: launch.{SHARDS_KEY}[{index}]"
        try:
            shard = parse_shard(name, index, entry)
        except SpanError as exc:
            raise UnitError(str(exc)) from exc
        rig, gpu, bind = shard.rig, shard.gpu, shard.bind
        scan = scans.get(rig)
        if scan is None:
            raise UnitError(
                f"{where}: host {rig!r} is unscanned — run `mcgyvr scan` on "
                f"{rig} before splitting a unit across its cards"
            )
        card = next((g for g in scan.gpus if g.index == gpu), None)
        if card is None:
            found = ", ".join(str(g.index) for g in scan.gpus) or "none"
            raise UnitError(
                f"{where}: {rig} has no card {gpu} in its scan (cards: {found})"
            )
        targets.append(
            Target(host=rig, gpu=gpu, free_bytes=card.vram.free_mib << 20, bind=bind)
        )
    return targets


def _stated_count(name: str, launch: Mapping[str, Any], field_name: str) -> int | None:
    ""
    stated = launch.get(field_name)
    if stated is None:
        return None
    if isinstance(stated, bool) or not isinstance(stated, int) or stated < 1:
        raise UnitError(f"{name}: launch.{field_name} is {stated!r}, not a count")
    return stated


def _stated_text(name: str, launch: Mapping[str, Any], field_name: str) -> str | None:
    stated = launch.get(field_name)
    if stated is None or isinstance(stated, str):
        return stated
    raise UnitError(f"{name}: launch.{field_name} is {stated!r}, not a word")


def _tensor_table(config: Config, name: str, stated: object) -> Mapping[str, Any]:
    ""
    if not isinstance(stated, str) or not stated:
        raise UnitError(
            f"{name}: a vLLM unit split across cards is sized from its tensor "
            f"table, and launch.tensor_table_json names none. Run python -m "
            f"mcgyvr.serving.safetensorscan <model dir> where the weights are "
            f"and point launch.tensor_table_json at what it printed"
        )
    where = Path(stated).expanduser()
    if not where.is_absolute() and config.path is not None:
        where = config.path / where
    try:
        raw = json.loads(where.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UnitError(f"{where}: cannot read a tensor table from it: {exc}") from exc
    rows = raw if isinstance(raw, list) else [raw]
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise UnitError(
            f"{where}: holds {len(rows)} rows; a vLLM unit's tensor table is one "
            f"safetensorscan row"
        )
    if "error" in rows[0]:
        raise UnitError(
            f"{where}: the scan could not read {rows[0].get('file')!r}: "
            f"{rows[0]['error']}"
        )
    table: dict[str, Any] = rows[0]
    return table


def alternate(one: Unit, other: Unit) -> bool:
    ""
    if one.host != other.host:
        return False
    if one.port == other.port:
        return True
    if one.cpu_only or other.cpu_only:
        #
        return False
    shared = set(one.cards) & set(other.cards)
    if shared and (len(one.cards) > 1 or len(other.cards) > 1):
        return True
    if not shared:
        #
        # a
        #
        return False
    free = _card_free_gb((one, other))
    if free <= 0:
        return False
    return one.fit.vram_gb + other.fit.vram_gb > free


def _card_free_gb(units: Iterable[Unit]) -> float:
    ""
    figures = [unit.fit.card_free_gb for unit in units if unit.fit.card_free_gb > 0]
    if not figures:
        return 0.0
    if any(unit.resident_claim_gb > 0 for unit in units):
        return max(figures)
    return min(figures)


def _co_resident(chosen: tuple[Unit, ...], candidate: Unit) -> bool:
    ""
    if any(alternate(unit, candidate) for unit in chosen):
        return False
    sharing = tuple(unit for unit in chosen if unit.gpu == candidate.gpu)
    free = _card_free_gb((*sharing, candidate))
    if free <= 0:
        return True
    asked = candidate.fit.vram_gb + sum(unit.fit.vram_gb for unit in sharing)
    return asked <= free


@dataclass(frozen=True)
class LaunchSpec:
    ""

    host: str
    units: tuple[Unit, ...]
    model: str | None = None


def launch_specs(units: Iterable[Unit]) -> tuple[LaunchSpec, ...]:
    ""
    on_host: dict[str, list[Unit]] = {}
    for unit in units:
        on_host.setdefault(unit.host, []).append(unit)

    specs: list[LaunchSpec] = []
    for host in sorted(on_host):
        here = tuple(
            sorted(on_host[host], key=lambda unit: (-unit.fit.vram_gb, unit.key.slug))
        )
        awake = tuple(unit for unit in here if not unit.asleep)
        if awake and len(awake) < len(here):
            #
            #
            #
            #
            awake_sets = _feasible(awake)
            if len(awake_sets) == 1 and len(awake_sets[0]) == len(awake):
                specs.append(
                    LaunchSpec(
                        host=host,
                        units=tuple(sorted(here, key=lambda unit: unit.key.slug)),
                    )
                )
                continue
            #
            #
            here = tuple(replace(unit, asleep=False) for unit in here)
        sets = _feasible(here)
        if len(sets) == 1 and len(sets[0]) == len(here):
            specs.append(LaunchSpec(host=host, units=sets[0]))
            continue
        for name, chosen in zip(_named(sets), sets, strict=True):
            specs.append(LaunchSpec(host=host, units=chosen, model=name))
    return tuple(specs)


def _feasible(here: tuple[Unit, ...]) -> tuple[tuple[Unit, ...], ...]:
    ""
    found: dict[tuple[str, ...], tuple[Unit, ...]] = {}
    for anchor in here:
        chosen: tuple[Unit, ...] = (anchor,)
        for other in here:
            if other.key == anchor.key:
                continue
            if _co_resident(chosen, other):
                chosen = (*chosen, other)
        settled = tuple(sorted(chosen, key=lambda unit: unit.key.slug))
        found.setdefault(tuple(unit.key.slug for unit in settled), settled)
    return tuple(found.values())


def _named(sets: tuple[tuple[Unit, ...], ...]) -> tuple[str, ...]:
    ""

    def defining(chosen: tuple[Unit, ...]) -> str:
        return max(chosen, key=lambda unit: (unit.fit.vram_gb, unit.key.slug)).model

    def every_model(chosen: tuple[Unit, ...]) -> str:
        return "_".join(sorted({unit.model for unit in chosen}))

    def with_ports(chosen: tuple[Unit, ...]) -> str:
        ports = "-".join(str(port) for port in sorted(unit.port for unit in chosen))
        return f"{every_model(chosen)}.{ports}"

    for spell in (defining, every_model, with_ports):
        names = tuple(spell(chosen) for chosen in sets)
        if len(set(names)) == len(names):
            return names
    #
    #
    #
    #
    raise UnitError(
        f"{sets[0][0].host}: two launch specs cannot be told apart by the "
        f"models and ports they hold, so they would be written to one file"
    )


def hold_together(units: Iterable[Unit], scans: Mapping[str, Scan]) -> tuple[str, ...]:
    ""
    warnings: list[str] = []
    for host, cut in _cut_into_alternatives(units).items():
        listed = ", ".join(
            f"{name} ({spec_name(host, name)})" for name in sorted(cut.keys())
        )
        warnings.append(
            f"{host}: {listed} do not sum onto the card and were emitted as "
            f"{len(cut)} alternatives — one launch spec each, and only one of "
            f"them is ever up. `serve up` takes one file, and mcgyvr will not "
            f"guess which: bring the one you mean up, and delete the "
            f"{spec_name(host)} an earlier emit may have left behind"
        )
    for spec in launch_specs(units):
        if len(spec.units) < 2 or spec.host not in scans:
            continue
        scan = scans[spec.host]
        free = _free_vram_bytes(scan) / _BYTES_PER_GIB
        on_card: dict[int, list[Unit]] = {}
        #
        #
        up = tuple(unit for unit in spec.units if not unit.asleep)
        for unit in up:
            on_card.setdefault(unit.gpu, []).append(unit)
        for sharing in on_card.values():
            if len(sharing) < 2:
                continue
            worst = sorted(sharing, key=lambda unit: unit.key.slug)
            asked = sum(unit.fit.vram_gb for unit in worst)
            if asked > free:
                listed = ", ".join(
                    f"{unit.model} ({unit.fit.vram_gb:.2f} GB)" for unit in worst
                )
                raise UnitError(
                    f"{spec.host}: {listed} fit the card one at a time and not "
                    f"together — {asked:.2f} GB summed against {free:.2f} GB "
                    f"free. Drop a unit, or state a smaller working set you "
                    f"have measured"
                )
        memory = scan.memory
        if memory is None:
            #
            #
            #
            continue
        hungriest = sorted(up, key=lambda unit: unit.key.slug)
        wanted = sum(unit.fit.ram_gb for unit in hungriest)
        #st
        #
        #
        #
        #
        margin = (
            REFUSAL_RAM_HEADROOM_GB
            if any(unit.engine not in MEDIA_ENGINES for unit in hungriest)
            else 0.0
        )
        if wanted and wanted + margin > memory.available_gb:
            listed = ", ".join(
                f"{unit.model} ({unit.fit.ram_gb:.2f} GB "
                f"{'unmapped' if unit.fit.load_mode == 'none' else 'mapped'})"
                for unit in hungriest
                if unit.fit.ram_gb
            )
            margin_clause = f" with {margin:.1f} GB held back" if margin else ""
            raise UnitError(
                f"{spec.host}: {listed} fit host memory one at a time and not "
                f"together — {wanted:.2f} GB summed{margin_clause}, against "
                f"{memory.available_gb:.2f} GB available. Serve one of them "
                f"from another host, drop one, or narrow a window"
            )
    return tuple(warnings)


def _cut_into_alternatives(units: Iterable[Unit]) -> dict[str, dict[str, None]]:
    ""
    specs = launch_specs(units)
    named: dict[str, dict[str, None]] = {}
    for spec in specs:
        if spec.model is None:
            continue
        named.setdefault(spec.host, {})[spec.model] = None
    return named


def safe_host(host: str) -> str:
    ""
    address = _ipv6(host)
    if address is not None:
        return _UNSAFE.sub("-", address)
    if not host or host != _UNSAFE.sub("-", host) or host in {".", ".."}:
        raise UnitError(f"{host!r} is not a host name a file can be named after")
    return host


def safe_model(model: str) -> str:
    ""
    name = _UNSAFE.sub("-", model)
    if not name or name in {".", ".."} or set(name) <= {"-"}:
        raise UnitError(f"{model!r} is not a model name a file can be named after")
    return name


def _ipv6(host: str) -> str | None:
    ""
    try:
        return ipaddress.IPv6Address(host).compressed
    except ValueError:
        return None


def spec_name(host: str, model: str | None = None) -> str:
    ""
    stem = (
        safe_host(host) if model is None else f"{safe_host(host)}.{safe_model(model)}"
    )
    return f"{COMPOSE_PREFIX}{stem}{COMPOSE_SUFFIX}"


def spec_files(root: Path, host: str) -> tuple[Path, ...]:
    ""
    try:
        whole = spec_name(host)
    except UnitError:
        #
        #
        return ()
    prefix = f"{whole[: -len(COMPOSE_SUFFIX)]}."
    try:
        found = [
            path
            for path in root.iterdir()
            if path.is_file()
            and path.name.endswith(COMPOSE_SUFFIX)
            and (path.name == whole or path.name.startswith(prefix))
        ]
    except OSError:
        return ()
    return tuple(sorted(found))


@dataclass(frozen=True)
class Card:
    ""

    host: str
    #'s
    #
    #
    #
    #
    #
    #
    #
    #
    compose_file: Path | None
    #`.
    #
    #
    specs: tuple[Path, ...] = ()
    #
    #
    #
    rungs: tuple[str, ...] = ()
    #
    #
    sources: tuple[str, ...] = ()


def cards(config: Config) -> dict[str, Card]:
    ""
    stated = config.get("serving.compose_dir")
    where = Path(str(stated)).expanduser() if stated else None

    rungs_on: dict[str, list[str]] = {}
    sources_on: dict[str, set[str]] = {}
    hosted: dict[str, str] = {}
    for name in config.ladder.names:
        unit = config.units.get(name)
        if unit is None or unit.requires_credential:
            continue
        host = host_of(unit.address)
        hosted[name] = host
        rungs_on.setdefault(host, []).append(name)
        sources_on.setdefault(host, set()).add(name)

    by_host = {
        host: Card(
            host=host,
            compose_file=where / spec_name(host) if where else None,
            specs=spec_files(where, host) if where else (),
            rungs=tuple(sorted(rungs_on[host])),
            sources=tuple(sorted(sources_on[host])),
        )
        for host in rungs_on
    }
    return {rung: by_host[host] for rung, host in hosted.items()}


def declared_models(config: Config) -> dict[str, ModelSpec]:
    ""
    specs: dict[str, ModelSpec] = {}
    for unit in config.units.values():
        name = unit.model
        if name in specs:
            continue
        if (
            not unit.launch
            and unit.hf_cache is None
            and unit.room_mib is None
            and unit.kv_cache_memory_bytes is None
        ):
            #
            continue
        block: dict[str, Any] = dict(unit.launch)
        if unit.hf_cache is not None:
            block.setdefault("hf_cache", unit.hf_cache)
        if unit.room_mib is not None and "vram_gb" not in block:
            block["vram_gb"] = unit.room_mib / 1024
        geometry: dict[str, Any] | None = None
        stated = block.get("geometry_json")
        if stated:
            where = Path(str(stated)).expanduser()
            if not where.is_absolute() and config.path is not None:
                where = config.path / where
            geometry = load_geometry(where, name=name)
        specs[name] = ModelSpec(
            name=name,
            vram_gb=block.get("vram_gb") or 0.0,
            ram_gb=block.get("ram_gb") or 0.0,
            disk_gb=block.get("disk_gb") or 0.0,
            vae_decode_gb=block.get("vae_decode_gb") or 0.0,
            cpu_only=bool(block.get("cpu_only")),
            moe=bool(block.get("moe")),
            geometry=geometry,
            hf_cache=str(block.get("hf_cache") or ""),
            serve_args=tuple(str(arg) for arg in (block.get("serve_args") or ())),
            kv_cache_dtype_k=block.get("kv_cache_dtype_k"),
            kv_cache_dtype_v=block.get("kv_cache_dtype_v"),
            speculative=str(block.get("speculative") or SPECULATIVE_NONE),
            spec_draft_n_max=_declared_draft_width(name, block.get("spec_draft_n_max")),
        )
    return specs


def _declared_draft_width(name: str, stated: object) -> int:
    ""
    if stated is None:
        return DEFAULT_SPEC_DRAFT_N_MAX
    if isinstance(stated, bool) or not isinstance(stated, int):
        raise UnitError(
            f"{name}: units.<unit>.launch.spec_draft_n_max is {stated!r}, and "
            f"--spec-draft-n-max is a count of tokens drafted per step"
        )
    return stated


#
#
_GEOMETRY_KEYS = (
    "file",
    "size_bytes",
    "n_layer",
    "bytes_nonexpert",
    "bytes_experts",
    "placeable_blocks",
    "expert_bytes_by_block",
    "kv_layers",
)


def load_geometry(path: Path | str, *, name: str | None = None) -> dict[str, Any]:
    ""
    where = Path(path)
    try:
        raw = json.loads(where.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UnitError(f"{where}: cannot read a geometry from it: {exc}") from exc

    if isinstance(raw, dict):
        rows: list[Any] = [raw]
    elif isinstance(raw, list):
        rows = raw
    else:
        raise UnitError(
            f"{where}: a geometry is one ggufscan row or a list of them, and this "
            f"is {type(raw).__name__}; re-scan: python -m mcgyvr.serving.ggufscan "
            f"<gguf>"
        )
    if not rows:
        raise UnitError(f"{where}: holds no geometry rows at all")
    if len(rows) == 1:
        row = rows[0]
    elif name is None:
        raise UnitError(
            f"{where}: holds {len(rows)} geometry rows and nothing says which "
            f"model to choose one for"
        )
    else:
        wanted = _weights_file_name(name)
        matched = [
            r
            for r in rows
            if isinstance(r, dict) and Path(str(r.get("file") or "")).name == wanted
        ]
        if len(matched) != 1:
            raise UnitError(
                f"{where}: {len(matched)} of {len(rows)} geometry rows were "
                f"scanned from {wanted!r}, and {name} needs exactly one"
            )
        row = matched[0]

    if not isinstance(row, dict):
        raise UnitError(f"{where}: a geometry row is a mapping, found {row!r}")
    if "error" in row:
        raise UnitError(
            f"{where}: ggufscan could not read {row.get('file')!r}: "
            f"{row['error']}. Nothing is sized from an error row; fix the file "
            f"and re-scan: python -m mcgyvr.serving.ggufscan <gguf>"
        )
    missing = [key for key in _GEOMETRY_KEYS if key not in row]
    if missing:
        raise UnitError(
            f"{where}: not a ggufscan row — it has no {', '.join(missing)}; "
            f"re-scan: python -m mcgyvr.serving.ggufscan <gguf>"
        )
    geometry: dict[str, Any] = row
    return geometry


def host_of(base_url: str) -> str:
    ""
    host = urlparse(base_url).hostname
    if not host:
        raise UnitError(f"no host in `units.<unit>.address` {base_url!r}")
    return host


def port_of(base_url: str) -> int:
    ""
    try:
        port = urlparse(base_url).port
    except ValueError as exc:
        raise UnitError(
            f"no usable port in `units.<unit>.address` {base_url!r}: {exc}"
        ) from exc
    return port if port is not None else DEFAULT_PORT


def _with_rungs(unit: Unit, rungs: tuple[str, ...]) -> Unit:
    ""
    return replace(unit, rungs=rungs)


def _roomiest_gpu(scan: Scan) -> Gpu:
    ""
    if not scan.gpus:
        raise UnitError(
            f"{scan.machine.host}: the scan found no GPU, so there is no card "
            "to place a unit on"
        )
    return max(scan.gpus, key=lambda gpu: gpu.vram.free_mib)


def _free_vram_bytes(scan: Scan) -> int:
    ""
    if not scan.gpus:
        return 0
    return max(gpu.vram.free_mib for gpu in scan.gpus) << 20


def _remaining_scan(scan: Scan, claim_gb: float) -> Scan:
    ""
    if claim_gb <= 0 or not scan.gpus:
        return scan
    claim_mib = int(claim_gb * 1024)
    gpus = list(scan.gpus)
    index = max(range(len(gpus)), key=lambda i: gpus[i].vram.free_mib)
    gpu = gpus[index]
    taken = min(claim_mib, gpu.vram.free_mib)
    #
    #
    gpus[index] = replace(
        gpu,
        vram=replace(
            gpu.vram,
            used_mib=gpu.vram.used_mib + taken,
            free_mib=gpu.vram.free_mib - taken,
        ),
    )
    return replace(scan, gpus=tuple(gpus))


def _allowance_gb(spec: ModelSpec) -> float:
    ""
    if spec.geometry is None:
        return DEFAULT_HEADROOM_GB
    return vramfit.SCRATCH_AND_CONTEXT_MIB / 1024


def _needs_geometry(spec: ModelSpec) -> str:
    return (
        f"{spec.name}: sizing an MoE needs its geometry: run "
        f"python -m mcgyvr.serving.ggufscan <gguf> and set "
        f"units.<unit>.launch.geometry_json, or point it at the envelope's "
        f"geometry.json. --n-cpu-moe moves whole blocks, and what each block's "
        f"experts weigh is in the tensor table and nowhere else — not in a "
        f"name, a parameter count or a file size"
    )


def _mtp_head_blocks(spec: ModelSpec) -> tuple[int, ...]:
    ""
    if spec.geometry is None:
        return ()
    return tuple(int(b) for b in spec.geometry.get("nextn_blocks") or ())


def _no_mtp_head(spec: ModelSpec) -> str:
    ""
    if spec.geometry is None:
        seen = f"{_weights_file_name(spec.name)!r} has not been scanned, so"
    else:
        seen = (
            f"{Path(str(spec.geometry.get('file') or '')).name!r} was scanned and "
            f"its tensor table has no nextn block, so"
        )
    return (
        f"{spec.name}: declares units.<unit>.launch.speculative: mtp, and {seen} "
        f"the GGUF carries no MTP head. --spec-type draft-mtp runs the head "
        f"grafted into the file, which is read off the tensor table "
        f"(ggufscan's nextn_blocks) and never assumed from a name; every "
        f"hardware-fitting stock GGUF scans 0 MTP tensors. Serve a grafted "
        f"checkpoint and point units.<unit>.launch.geometry_json at its scan, "
        f"or set speculative: none"
    )


@dataclass(frozen=True)
class _Placement:
    ""

    n_cpu_moe: int
    width: int
    vram_gb: float
    ram_gb: float
    headroom_gb: float
    #
    head_bytes: int = 0


def _placement(
    spec: ModelSpec,
    free_bytes: int,
    width: int | None = None,
    *,
    engine: str,
    host: str,
    ctx_per_slot: int,
    n_ubatch: int = DEFAULT_UBATCH,
) -> _Placement:
    ""
    if spec.geometry is None:
        if spec.moe:
            raise UnitError(_needs_geometry(spec))
        return _Placement(
            n_cpu_moe=0,
            width=width if width is not None else 1,
            vram_gb=spec.vram_gb,
            ram_gb=spec.ram_gb,
            headroom_gb=DEFAULT_HEADROOM_GB,
        )

    geometry = dict(spec.geometry)
    #
    #
    #
    #
    #
    head_bytes = (
        vramfit.mtp_head_bytes(geometry) if spec.speculative == SPECULATIVE_MTP else 0
    )

    def constant(slots: int) -> int:
        try:
            kv_total = kv_bytes_for_run(
                ctx_per_slot=ctx_per_slot,
                slots=slots,
                geometry=geometry,
                n_ubatch=n_ubatch,
                cache_type_k=spec.kv_cache_dtype_k or "f16",
                cache_type_v=spec.kv_cache_dtype_v or "f16",
            )
            rs = vramfit.rs_bytes(geometry, n_seq_max=slots)
        except ValueError as exc:
            #
            #
            #
            raise UnitError(
                f"{spec.name}: the cache cannot be sized, so nothing is placed "
                f"from an invented split: {exc}"
            ) from exc
        return (
            int(geometry["bytes_nonexpert"])
            + head_bytes
            + kv_total
            + rs["total"]
            + (vramfit.SCRATCH_AND_CONTEXT_MIB << 20)
        )

    def floor_at(slots: int) -> int | None:
        return vramfit.floor(geometry, free_bytes, constant(slots))

    if width is not None:
        slots = width
        n_cpu_moe = floor_at(slots)
    else:
        n_cpu_moe = floor_at(1)
        slots = (
            max(w for w in range(1, MAX_WIDTH + 1) if floor_at(w) == n_cpu_moe)
            if n_cpu_moe is not None
            else 1
        )
    if n_cpu_moe is None:
        raise UnitError(
            f"{spec.name}: does not fit at any offload on a card with "
            f"{free_bytes >> 20} MiB free at {slots} slot(s): the non-expert "
            f"weights, cache, state and scratch alone want "
            f"{constant(slots) >> 20} MiB with every expert block off the card. "
            f"This is the card being too small, not the config being wrong"
        )
    card = vramfit.predict(geometry, n_cpu_moe, constant(slots))
    return _Placement(
        n_cpu_moe=n_cpu_moe,
        width=slots,
        vram_gb=card / _BYTES_PER_GIB,
        ram_gb=max(
            spec.ram_gb, _host_gb(geometry, n_cpu_moe, engine=engine, host=host)
        ),
        headroom_gb=vramfit.SCRATCH_AND_CONTEXT_MIB / 1024,
        head_bytes=head_bytes,
    )


def _host_gb(
    geometry: dict[str, Any], n_cpu_moe: int, *, engine: str, host: str
) -> float:
    ""
    offloaded = int(geometry["bytes_experts"]) - vramfit.experts_on_card(
        geometry, n_cpu_moe
    )
    if offloaded <= 0:
        return 0.0
    if engine in derived.RUNTIME_RESIDENT_READ:
        return offloaded / _BYTES_PER_GIB
    try:
        resident = derived.runtime_resident_gb(host)
    except derived.DerivedNumbersError as exc:
        raise UnitError(str(exc)) from exc
    return offloaded / _BYTES_PER_GIB + resident


def _window_for(
    key: UnitKey, declared: Mapping[int, list[str]], ctx_per_slot: int | None
) -> int:
    ""
    if len(declared) > 1:
        pairs = ", ".join(
            f"{window} ({', '.join(sorted(names))})"
            for window, names in sorted(declared.items())
        )
        raise UnitError(
            f"{key.slug}: one process, {len(declared)} declared context "
            f"windows — {pairs}. These units name one URL, so one window "
            f"would silently lose and the unit behind it would be served a "
            f"window its contracts were never priced against. Point them at "
            f"one window, or at two ports"
        )
    if declared:
        ((window, names),) = declared.items()
        if ctx_per_slot is not None and ctx_per_slot != window:
            raise UnitError(
                f"{names[0]}: declares window {window} and this run "
                f"was told {ctx_per_slot}. Both numbers are in hand and they "
                f"are two different launches, so neither is preferred here: "
                f"edit the unit if the rig moved, or drop the flag if it "
                f"did not"
            )
        return window
    if ctx_per_slot is None:
        raise UnitError(
            f"{key.slug}: no context window was declared for this run and its "
            f"unit declares none, so nothing can be sized: the cache, the "
            f"`-c` on the argv and the `--n-cpu-moe` floor are all priced "
            f"against it, and a window this module chose would be a number "
            f"nobody measured. Declare it — read it back off the running unit "
            f"(`max_model_len` on vLLM, `n_ctx` on llama.cpp) and state what "
            f"it said"
        )
    return ctx_per_slot


def _offload_note(spec: ModelSpec, placed: _Placement) -> str:
    ""
    if spec.geometry is None or not spec.moe:
        return ""
    placeable = list(spec.geometry["placeable_blocks"])
    on_card = sum(1 for block in placeable if block >= placed.n_cpu_moe)
    return (
        f" (--n-cpu-moe {placed.n_cpu_moe}: {on_card} of {len(placeable)} expert "
        f"blocks on the card)"
    )


def _threads(scan: Scan) -> int:
    ""
    if scan.cpu is None:
        return 1
    return max(1, min(scan.cpu.cores or scan.cpu.threads, scan.cpu.threads))


def _weights_file_name(name: str) -> str:
    ""
    return f"{name.replace('/', '_')}.gguf"


def _weights_path(scan: Scan, spec: ModelSpec) -> Path:
    ""
    root = scan.disk.path if scan.disk is not None else default_weights_dir()
    return root / _weights_file_name(spec.name)


def kv_bytes_for_run(
    *,
    ctx_per_slot: int,
    slots: int,
    geometry: Mapping[str, Any] | None = None,
    n_ubatch: int = DEFAULT_UBATCH,
    cache_type_k: str = "f16",
    cache_type_v: str = "f16",
) -> int:
    ""
    if ctx_per_slot < 1 or slots < 1:
        raise UnitError(
            f"a cache cannot be sized at {ctx_per_slot} context across "
            f"{slots} slot(s): both are counts of something a process holds"
        )
    extent = ctx_per_slot * slots
    if geometry is None:
        return extent
    return int(
        vramfit.kv_bytes(
            dict(geometry),
            extent,
            n_seq_max=slots,
            n_ubatch=n_ubatch,
            cache_type_k=cache_type_k,
            cache_type_v=cache_type_v,
        )["total"]
    )


def served_window(reported: Mapping[str, Any]) -> int | None:
    ""
    models = reported.get("data")
    if isinstance(models, list):
        for entry in models:
            if not isinstance(entry, Mapping):
                continue
            window = entry.get("max_model_len")
            if isinstance(window, int) and not isinstance(window, bool):
                return window
    window = reported.get("n_ctx")
    if isinstance(window, int) and not isinstance(window, bool):
        return window
    return None
