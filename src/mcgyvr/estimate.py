"""First-run estimates of a device: its usable unified memory and a decode speed.

Every figure here says what it is (`Figure.figure`, one of
:data:`mcgyvr.hubwire.FIGURE_KINDS`): an ``estimate`` until the machine's own
``reading`` exists, and a reading always wins (:func:`prefer`). An estimate
names its basis, so the user can see what it was worked out from.

The decode estimate is memory bandwidth over the bytes a token reads, times an
efficiency (:data:`DECODE_EFFICIENCY`). The rule is the wire's
(:mod:`mcgyvr.hubwire`), where the hub reads it too. Bandwidth comes from the
device's class in the shipped table ``hardware-classes.json`` (Apple silicon
chips and NVIDIA consumer cards, each row with its source); a device that
matches no row gets no estimate, and :class:`NoEstimate` says why.

For one line (a model file at a context and a slot count) on one device, three
figures from numbers passed in: decode (:func:`decode_tps`, with the engine
build and the cache of a filled context when given), prefill
(:func:`prefill_tps`, the device's rate over the work a token takes) and the fit
(:func:`line_fit`, the launch check's own verdict from the file's header). A
build, path or input with no fit gets no figure, and :class:`NoEstimate` names
what is missing.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from mcgyvr.hubwire import (
    BACKEND_CUDA,
    BACKEND_METAL,
    DECODE_SHARES,
    FIGURE_KINDS,
    decode_efficiency,
    decode_share,
    quant_class,
)
from mcgyvr.hubwire import BYTES_PER_DECIMAL_GB as BYTES_PER_DECIMAL_GB
from mcgyvr.hubwire import CUDA_SCOREBOARD as CUDA_SCOREBOARD
from mcgyvr.hubwire import DECODE_EFFICIENCY as DECODE_EFFICIENCY
from mcgyvr.hubwire import FIGURE_ESTIMATE as ESTIMATE
from mcgyvr.hubwire import FIGURE_READING as READING
from mcgyvr.hubwire import FITTED_ON as FITTED_ON
from mcgyvr.hubwire import HIGH_BANDWIDTH_EFFICIENCY as HIGH_BANDWIDTH_EFFICIENCY
from mcgyvr.hubwire import HIGH_BANDWIDTH_GBPS as HIGH_BANDWIDTH_GBPS
from mcgyvr.hubwire import PATH_MATRIX as PATH_MATRIX
from mcgyvr.hubwire import PATH_VECTOR as PATH_VECTOR
from mcgyvr.hubwire import FittedShare as FittedShare
from mcgyvr.shipped import shipped_file

if TYPE_CHECKING:
    from mcgyvr.scan import Scan
    from mcgyvr.serving import Fit

CLASSES_FILENAME = "hardware-classes.json"

#: The decode efficiency for a bandwidth, quantisation and vendor: the wire's.
efficiency = decode_efficiency

#: The version of the table's format this code reads.
CLASSES_SCHEMA = 1


class HardwareClassesError(Exception):
    """The shipped table cannot be read, or is not the shape declared here."""


@dataclass(frozen=True)
class Figure:
    """A number and what it is: an ``estimate`` or a ``reading``, and its basis."""

    value: float
    figure: str
    basis: str
    #: False when the estimate rests on a table row whose source could not be
    #: read cleanly; a reading is always verified.
    verified: bool = True

    def __post_init__(self) -> None:
        if self.figure not in FIGURE_KINDS:
            raise ValueError(f"figure must be one of {FIGURE_KINDS}: {self.figure!r}")


@dataclass(frozen=True)
class NoEstimate:
    """No estimate can be made, and why."""

    why: str


@dataclass(frozen=True)
class HardwareClass:
    """One row of the shipped table: a device class and its memory bandwidth."""

    id: str
    vendor: str
    name: str
    bandwidth_gbps: float
    verified: bool
    url: str
    gpu_cores: tuple[int, ...] = ()
    vram_gb: int | None = None
    match_memory_gb: tuple[int, ...] = ()


#: What the filled-context term of :func:`decode_tps` was checked on: the one
#: public row found (llama-bench on an NVIDIA Thor, a 30B MoE at Q8_0 with an
#: f16 cache, from an empty context to 32k tokens).
CACHE_TERM_CHECK = (
    "the cache term, checked on one public row "
    "(https://github.com/ggml-org/llama.cpp/discussions/16578), reads slow by 9% "
    "at 16k tokens and 13% at 32k"
)


def decode_tps(
    bandwidth_gbps: float,
    model_bytes: int,
    quant: str,
    *,
    verified: bool = True,
    device: str = "",
    vendor: str = FITTED_ON,
    build: str | None = None,
    path: str | None = None,
    cache_bytes: int = 0,
) -> Figure | NoEstimate:
    """Estimated decode tokens per second of a dense model on one device.

    ``efficiency x bandwidth_gbps / (model_bytes / 1e9)``: each token reads every
    weight once, at the share of the bandwidth :data:`DECODE_EFFICIENCY` states
    for the quantisation. A quantisation with no efficiency class, or a
    non-positive size or bandwidth, gets no estimate.

    ``build`` and ``path`` name the engine build and its compute path, for the
    share fitted under that build (:func:`mcgyvr.hubwire.decode_efficiency`);
    unnamed, the figure is today's. ``cache_bytes`` is the cache a token reads
    beside the weights, the filled context's (:func:`context_bytes`); 0 reads
    none. That term is checked on one public row only (:data:`CACHE_TERM_CHECK`),
    which runs faster than it says at 16k and 32k tokens.
    """
    if bandwidth_gbps <= 0 or model_bytes <= 0:
        return NoEstimate("no bandwidth or model size to estimate decode from")
    if cache_bytes < 0:
        return NoEstimate("the cache a token reads cannot be negative")
    eff = efficiency(bandwidth_gbps, quant, vendor=vendor, build=build, path=path)
    if eff is None:
        if build is not None and build != BACKEND_METAL:
            return _no_decode_share(build, path, quant)
        return NoEstimate(
            f"no decode estimate for quantisation {quant!r}: the rule was fitted "
            "to 16-, 8- and 4- to 6-bit weights"
        )
    on = f"{device}, " if device else ""
    fitted = "" if vendor == FITTED_ON else ", shares fitted on Apple silicon"
    if build is not None and build != BACKEND_METAL:
        fitted = _fitted_on(build, path, decode_share(build, path, quant))
    gb = (model_bytes + cache_bytes) / BYTES_PER_DECIMAL_GB
    read = ""
    if cache_bytes:
        read = (
            f" ({model_bytes / BYTES_PER_DECIMAL_GB:.2f} GB of weights and "
            f"{cache_bytes / BYTES_PER_DECIMAL_GB:.2f} GB of cache; "
            f"{CACHE_TERM_CHECK})"
        )
    return Figure(
        eff * bandwidth_gbps / gb,
        ESTIMATE,
        f"{on}{bandwidth_gbps:g} GB/s x {eff:g} over {gb:.2f} GB read per "
        f"token{read}{fitted}",
        verified=verified,
    )


def _fitted_on(build: str, path: str | None, share: FittedShare | None) -> str:
    """What a fitted share is: its build, its path, and the spread behind it."""
    if share is None:
        return ""
    return (
        f", the {build} share on the {path} path: the median of {share.cards} "
        f"cards, {share.low:g} to {share.high:g} (furthest: {share.worst}), "
        f"{share.source}"
    )


def _no_decode_share(build: str, path: str | None, quant: str) -> NoEstimate:
    """Why a build gets no decode share: the input that is missing or unfitted."""
    if build not in DECODE_SHARES:
        return NoEstimate(
            f"no decode share for the {build} build: none is fitted on a public "
            "table yet"
        )
    if path is None:
        return NoEstimate(
            f"the {build} build's compute path on this device is unknown, so no "
            "decode share"
        )
    if path not in DECODE_SHARES[build]:
        return NoEstimate(f"no {build} decode share on the {path} path")
    return NoEstimate(
        f"no {build} decode share for quantisation {quant!r} "
        f"(class {quant_class(quant)}): its fit was on 4-bit files only"
    )


def context_bytes(
    header: Mapping[str, Any], tokens: int, *, cache_type: str = "f16"
) -> int | NoEstimate:
    """The cache bytes one decoded token reads after ``tokens`` of context, at
    ``cache_type`` for K and V: the fit law's own cache figure for one sequence
    (:func:`mcgyvr.serving.vramfit.kv_bytes`), from the file's header row, so a
    sliding layer is charged its window and no more."""
    from mcgyvr.serving import vramfit

    if tokens < 0:
        return NoEstimate("a context cannot hold fewer than 0 tokens")
    if cache_type not in vramfit.CACHE_ELEM_BYTES:
        return NoEstimate(
            f"cache type {cache_type!r} has no width; llama.cpp takes "
            f"{', '.join(vramfit.LLAMACPP_CACHE_TYPES)}"
        )
    if not header.get("kv_layers"):
        return NoEstimate("the header states no caching layers, so no cache figure")
    try:
        sized = vramfit.kv_bytes(
            dict(header),
            tokens,
            n_seq_max=1,
            cache_type_k=cache_type,
            cache_type_v=cache_type,
        )
    except (KeyError, TypeError, ValueError) as exc:
        return NoEstimate(f"the header's cache cannot be sized: {exc}")
    return int(sized["total"])


#: The prefill shares of an engine build, by compute path: 2 x the parameters x
#: pp512 over the card's rate (the matrix units' FP16 rate on the matrix path,
#: the FP32 rate on the vector path), the median over the CUDA scoreboard's cards
#: the shipped hardware table names (``tools/speed-shares/fit_shares.py``). A
#: share over 1 says the build ran faster than that rate. Fitted on a dense 7B
#: model at Q4_0, one slot, a 512-token prompt; Metal and every other build have
#: none yet.
PREFILL_SHARES: Mapping[str, Mapping[str, FittedShare]] = MappingProxyType(
    {
        BACKEND_CUDA: MappingProxyType(
            {
                PATH_MATRIX: FittedShare(
                    1.049, 17, 0.666, 1.136, "RTX 2060 SUPER 8 GB", CUDA_SCOREBOARD
                ),
                PATH_VECTOR: FittedShare(
                    1.176, 3, 0.399, 1.29, "GTX 1660 6 GB", CUDA_SCOREBOARD
                ),
            }
        )
    }
)
#: What each path's rate is, by name, for a figure's basis and a refusal.
PATH_RATES: Mapping[str, str] = MappingProxyType(
    {PATH_MATRIX: "matrix FP16", PATH_VECTOR: "FP32"}
)


def prefill_params(header: Mapping[str, Any]) -> int | NoEstimate:
    """The parameters a prompt token is computed through, from the file's header
    row: all of them for a dense model. A mixture of experts gets none: the
    prefill share was fitted on a dense model only."""
    experts = header.get("n_expert")
    if isinstance(experts, int) and not isinstance(experts, bool) and experts > 0:
        return NoEstimate(
            "a mixture of experts: the prefill share was fitted on dense models only"
        )
    params = header.get("params_total")
    if not isinstance(params, int) or isinstance(params, bool) or params <= 0:
        return NoEstimate("the header states no parameter count")
    return params


def prefill_tps(
    rate_tflops: float | None,
    params: int | None,
    *,
    build: str | None,
    path: str | None,
    device: str = "",
    verified: bool = True,
) -> Figure | NoEstimate:
    """Estimated prefill tokens per second of a dense model on one device.

    ``share x rate_tflops / (2 x params)``: a prompt token takes two operations
    per parameter, and the device does them at the share of its rate on the
    path the build takes there (:data:`PREFILL_SHARES`, :data:`PATH_RATES`). A
    build or path with no share, an unknown rate or an unknown parameter count
    gets no estimate, and says which.
    """
    if build is None:
        return NoEstimate("the engine build is unknown, so no prefill share")
    if build not in PREFILL_SHARES:
        return NoEstimate(
            f"no prefill share for the {build} build: none is fitted on a public "
            "table yet"
        )
    if path is None:
        return NoEstimate(
            f"the {build} build's compute path on this device is unknown, so no "
            "prefill share"
        )
    share = PREFILL_SHARES[build].get(path)
    if share is None:
        return NoEstimate(f"no {build} prefill share on the {path} path")
    if rate_tflops is None or not rate_tflops > 0:
        return NoEstimate(f"the device's {PATH_RATES[path]} rate is unknown")
    if params is None or params <= 0:
        return NoEstimate("the model's parameter count is unknown")
    on = f"{device}, " if device else ""
    return Figure(
        share.value * rate_tflops * 1e12 / (2 * params),
        ESTIMATE,
        f"{on}{rate_tflops:g} TFLOPS {PATH_RATES[path]} x {share.value:g} over 2 x "
        f"{params / 1e9:.2f}B parameters, a short prompt at one slot"
        f"{_fitted_on(build, path, share)}",
        verified=verified,
    )


def line_fit(
    scan: Scan,
    header: Mapping[str, Any],
    *,
    ctx_per_slot: int,
    slots: int = 1,
    cache_type: str = "f16",
) -> Fit | NoEstimate:
    """Whether a model file fits the machine of ``scan`` at ``slots`` of
    ``ctx_per_slot`` each, before it is downloaded: the launch check itself
    (:func:`mcgyvr.serving.fit`, a llama.cpp unit on the roomiest card) on the
    file's header row as its geometry, at ``cache_type`` for K and V. So the
    verdict here is the one the launch check gives once the file is on disk. A
    header the law cannot size gets no verdict, and says why; a ``Fit`` that
    does not fit is a no, with the law's reason."""
    from mcgyvr.config import DEFAULT_ENGINE
    from mcgyvr.hubwire import BYTES_PER_GIB
    from mcgyvr.serving import ModelSpec, UnitError, fit, vramfit

    if ctx_per_slot < 1 or slots < 1:
        return NoEstimate("a context and a slot count are counts, so at least 1")
    if cache_type not in vramfit.CACHE_ELEM_BYTES:
        return NoEstimate(
            f"cache type {cache_type!r} has no width; llama.cpp takes "
            f"{', '.join(vramfit.LLAMACPP_CACHE_TYPES)}"
        )
    size = header.get("size_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        return NoEstimate("the header states no file size")
    try:
        spec = ModelSpec(
            name=Path(str(header.get("file") or "")).name.removesuffix(".gguf"),
            vram_gb=0.0,
            ram_gb=0.0,
            disk_gb=size / BYTES_PER_GIB,
            geometry=dict(header),
            kv_cache_dtype_k=cache_type,
            kv_cache_dtype_v=cache_type,
        )
        return fit(
            scan,
            spec,
            engine=DEFAULT_ENGINE,
            width=slots,
            ctx_per_slot=ctx_per_slot,
        )
    except (UnitError, KeyError, TypeError, ValueError) as exc:
        return NoEstimate(f"the fit law cannot size this header: {exc}")


def prefer(
    reading: float | None,
    estimate: Figure | NoEstimate,
    *,
    where: str = "this machine",
) -> Figure | NoEstimate:
    """The reading taken at ``where`` when there is one, else the estimate."""
    if reading is not None and reading > 0:
        return Figure(float(reading), READING, f"measured at {where}")
    return estimate


def classes_path() -> Path:
    """Where the shipped table is: the package's copy, else the checkout's."""
    found = shipped_file(CLASSES_FILENAME)
    if found is None:
        raise HardwareClassesError(f"{CLASSES_FILENAME} not found")
    return found


_TOP_KEYS = frozenset({"_doc", "schema_version", "classes", "_sources"})
_ROW_KEYS = frozenset(
    {
        "id",
        "vendor",
        "name",
        "bandwidth_gbps",
        "verified",
        "source",
        "gpu_cores",
        "match_memory_gb",
        "vram_gb",
        "note",
    }
)
_VENDORS = ("apple", "nvidia")


def _row(raw: Any, sources: Mapping[str, Any], where: Path) -> HardwareClass:
    if not isinstance(raw, dict):
        raise HardwareClassesError(f"{where}: a class row is not an object: {raw!r}")
    rid = raw.get("id")
    unknown = sorted(set(raw) - _ROW_KEYS)
    if unknown:
        raise HardwareClassesError(f"{where}: row {rid!r} carries undeclared {unknown}")
    if raw.get("vendor") not in _VENDORS:
        raise HardwareClassesError(
            f"{where}: row {rid!r} vendor is not one of {_VENDORS}"
        )
    bandwidth = raw.get("bandwidth_gbps")
    if (
        isinstance(bandwidth, bool)
        or not isinstance(bandwidth, int | float)
        or bandwidth <= 0
    ):
        raise HardwareClassesError(
            f"{where}: row {rid!r} bandwidth_gbps is not positive"
        )
    if not isinstance(raw.get("verified"), bool):
        raise HardwareClassesError(
            f"{where}: row {rid!r} verified is not true or false"
        )
    source = sources.get(str(raw.get("source")))
    if (
        not isinstance(source, dict)
        or not str(source.get("url", "")).startswith("https://")
        or not (source.get("quote") or source.get("summary"))
    ):
        raise HardwareClassesError(
            f"{where}: row {rid!r} has no https source with a quote or a summary "
            "in _sources"
        )
    if raw["vendor"] == "nvidia" and not isinstance(raw.get("vram_gb"), int):
        raise HardwareClassesError(f"{where}: NVIDIA row {rid!r} states no vram_gb")
    return HardwareClass(
        id=str(rid),
        vendor=raw["vendor"],
        name=str(raw.get("name")),
        bandwidth_gbps=float(bandwidth),
        verified=raw["verified"],
        url=source["url"],
        gpu_cores=tuple(raw.get("gpu_cores") or ()),
        vram_gb=raw.get("vram_gb"),
        match_memory_gb=tuple(raw.get("match_memory_gb") or ()),
    )


def load_classes(path: Path | None = None) -> tuple[HardwareClass, ...]:
    """Read and check the table at ``path``, defaulting to :func:`classes_path`."""
    where = path or classes_path()
    try:
        raw = json.loads(where.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HardwareClassesError(f"cannot read {where}: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != CLASSES_SCHEMA:
        raise HardwareClassesError(f"{where}: not schema {CLASSES_SCHEMA}")
    unknown = sorted(set(raw) - _TOP_KEYS)
    if unknown:
        raise HardwareClassesError(f"{where}: undeclared keys {unknown}")
    sources = raw.get("_sources")
    rows = raw.get("classes")
    if not isinstance(sources, dict) or not isinstance(rows, list) or not rows:
        raise HardwareClassesError(
            f"{where}: needs a classes list and a _sources object"
        )
    found = tuple(_row(row, sources, where) for row in rows)
    ids = [one.id for one in found]
    if len(set(ids)) != len(ids):
        raise HardwareClassesError(f"{where}: a class id is stated twice")
    return found


@cache
def shipped_classes() -> tuple[HardwareClass, ...]:
    """The shipped table, read once."""
    return load_classes()


#: Words a device's name may carry that no class is named with: a vendor's and
#: a product line's names before the model, and "GPU" after it.
_VENDOR_WORDS = re.compile(r"^(?:(?:nvidia|geforce|apple)\s+)+", re.IGNORECASE)
_GPU_WORD = re.compile(r"\s+gpu$", re.IGNORECASE)


def class_name(name: str) -> str:
    """The name a device is looked up by: ``NVIDIA GeForce RTX 3080`` is
    ``rtx 3080``, ``Apple M2 Max GPU`` is ``m2 max``."""
    plain = " ".join(name.split())
    return _GPU_WORD.sub("", _VENDOR_WORDS.sub("", plain)).lower()


def variants(
    name: str,
    *,
    vram_mib: int | None = None,
    gpu_cores: int | None = None,
    memory_mib: int | None = None,
    classes: tuple[HardwareClass, ...] | None = None,
) -> tuple[HardwareClass, ...] | NoEstimate:
    """The classes a device may be, by its name and what tells its variants apart.

    The name is matched whole, without vendor words (:func:`class_name`), so
    ``RTX 4060 Ti`` never matches ``RTX 4060``, nor ``RTX 4090 Laptop GPU``
    ``RTX 4090``. Rows of one name that state ``vram_gb`` are told apart by
    the card's memory in whole GB, and a card whose memory is unread or
    matches none gets no class. Rows that state GPU cores are told apart by
    the cores, and rows that state ``match_memory_gb`` by the machine's
    memory, when those are read; what is left may be more than one row. A
    name no row has gets no class.
    """
    table = classes if classes is not None else shipped_classes()
    key = class_name(name)
    rows = [one for one in table if class_name(one.name) == key]
    if not rows:
        return NoEstimate(f"{name}: no bandwidth class for this device, so no estimate")
    if any(one.vram_gb is not None for one in rows):
        if vram_mib is None:
            return NoEstimate(
                f"{name}: its memory is unread, so its variant is unknown and no "
                "estimate is made"
            )
        gb = round(vram_mib / 1024)
        rows = [one for one in rows if one.vram_gb == gb]
        if not rows:
            return NoEstimate(
                f"{name} with {gb} GB: no bandwidth class for this variant"
            )
    if gpu_cores is not None:
        rows = [one for one in rows if gpu_cores in one.gpu_cores] or rows
    if memory_mib is not None and any(one.match_memory_gb for one in rows):
        gb = round(memory_mib / 1024)
        rows = [one for one in rows if gb in one.match_memory_gb] or rows
    return tuple(rows)


def match(
    name: str,
    *,
    vram_mib: int | None = None,
    gpu_cores: int | None = None,
    memory_mib: int | None = None,
    classes: tuple[HardwareClass, ...] | None = None,
) -> HardwareClass | NoEstimate:
    """The class of a device (:func:`variants`); of several, the one with the
    lowest bandwidth, so an unread variant is never estimated fast."""
    found = variants(
        name,
        vram_mib=vram_mib,
        gpu_cores=gpu_cores,
        memory_mib=memory_mib,
        classes=classes,
    )
    if isinstance(found, NoEstimate):
        return found
    return min(found, key=lambda one: one.bandwidth_gbps)


def token_bytes(size_bytes: int, geometry: Mapping[str, Any] | None = None) -> int:
    """The weight bytes one decoded token reads: the whole file for a dense model;
    for a mixture of experts whose geometry states its experts, the non-expert
    bytes plus the share of the expert bytes its used experts make up."""
    if geometry:
        experts = geometry.get("n_expert")
        used = geometry.get("n_expert_used")
        expert_bytes = geometry.get("bytes_experts")
        nonexpert = geometry.get("bytes_nonexpert")
        if (
            isinstance(experts, int)
            and isinstance(used, int)
            and isinstance(expert_bytes, int)
            and isinstance(nonexpert, int)
            and 0 < used <= experts
        ):
            return nonexpert + expert_bytes * used // experts
    return size_bytes


def device_decode(
    name: str,
    *,
    model_bytes: int,
    quant: str | None,
    vram_mib: int | None = None,
    gpu_cores: int | None = None,
    memory_mib: int | None = None,
    reading: float | None = None,
    where: str = "this machine",
    classes: tuple[HardwareClass, ...] | None = None,
) -> Figure | NoEstimate:
    """A model's decode speed on a named device: the reading taken at ``where``
    when there is one, else the estimate from the device's class (the slower
    variant, and said so, when the device could be more than one), else why
    there is none."""
    return prefer(
        reading,
        _class_decode(
            name,
            model_bytes=model_bytes,
            quant=quant,
            vram_mib=vram_mib,
            gpu_cores=gpu_cores,
            memory_mib=memory_mib,
            classes=classes,
        ),
        where=where,
    )


def _class_decode(
    name: str,
    *,
    model_bytes: int,
    quant: str | None,
    vram_mib: int | None,
    gpu_cores: int | None,
    memory_mib: int | None,
    classes: tuple[HardwareClass, ...] | None,
) -> Figure | NoEstimate:
    """The estimate from the device's class, or why there is none."""
    found = variants(
        name,
        vram_mib=vram_mib,
        gpu_cores=gpu_cores,
        memory_mib=memory_mib,
        classes=classes,
    )
    if isinstance(found, NoEstimate):
        return found
    slowest = min(found, key=lambda one: one.bandwidth_gbps)
    device = f"class {slowest.id}"
    if len(found) > 1:
        device += f", the slower of {len(found)} variants its reading cannot tell apart"
    if not quant:
        return NoEstimate(
            f"{name}: the model's quantisation is unknown, so no estimate"
        )
    return decode_tps(
        slowest.bandwidth_gbps,
        model_bytes,
        quant,
        verified=slowest.verified,
        device=device,
        vendor=slowest.vendor,
    )
