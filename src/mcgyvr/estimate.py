"""First-run estimates of a device: its usable unified memory and a decode speed.

Every figure here says what it is (`Figure.figure`, one of
:data:`mcgyvr.hubwire.FIGURE_KINDS`): an ``estimate`` until the machine's own
``reading`` exists, and a reading always wins (:func:`prefer`). An estimate
names its basis, so the user can see what it was worked out from.

The decode estimate is memory bandwidth over the bytes a token reads, times an
efficiency (:data:`DECODE_EFFICIENCY`). Bandwidth comes from the device's class
in the shipped table ``hardware-classes.json`` (Apple silicon chips and NVIDIA
consumer cards, each row with its source); a device that matches no row gets no
estimate, and :class:`NoEstimate` says why.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from mcgyvr.hubwire import FIGURE_KINDS
from mcgyvr.shipped import shipped_file

CLASSES_FILENAME = "hardware-classes.json"

#: The version of the table's format this code reads.
CLASSES_SCHEMA = 1

ESTIMATE, READING = FIGURE_KINDS

#: Bytes in the decimal GB a bandwidth in GB/s is stated in.
BYTES_PER_GB = 1e9

#: The share of a Mac's memory its GPU may wire when the kernel's own limit is in
#: force (``iogpu.wired_limit_mb`` is 0): llama.cpp treats Metal's
#: ``recommendedMaxWorkingSetSize`` as the device's total, and a 192 GB machine
#: logs 75.1% of its memory there
#: (https://github.com/ggml-org/llama.cpp/discussions/9784); the exact kernel
#: rule has no Apple source, so this share is an estimate. The machine reader
#: (``serving/rigscan.py`` ``UNIFIED_SHARE``, standalone) spells the same value.
UNIFIED_SHARE = 0.75

#: Decode efficiency: measured text-generation speed over the speed the
#: bandwidth alone would allow, ``tg x model_GB / bandwidth_GBps``. Fitted to
#: llama.cpp's own Apple-silicon table, llama-bench tg128 of a dense 7B model at
#: F16, Q8_0 and Q4_0 over M1..M4 (llama.cpp discussion 4167,
#: https://github.com/ggml-org/llama.cpp/discussions/4167): medians 0.83 (F16),
#: 0.79 (Q8_0) and 0.69 (Q4_0), falling as the quantisation shrinks (dequant
#: cost) and as bandwidth rises (an 800 GB/s part is compute-bound on a 7B
#: model: 0.36..0.71). The values below sit under those medians, so an estimate
#: errs slow: 0.75 for 16-bit and 8-bit weights, 0.60 for 4-bit to 6-bit ones
#: (Q5/Q6 were not measured; they take the 4-bit figure, the lower of the two
#: they sit between), and at most :data:`HIGH_BANDWIDTH_EFFICIENCY` from
#: :data:`HIGH_BANDWIDTH_GBPS` up. A current llama.cpp build runs about 1.2x
#: faster than the build those rows used; no allowance is made for it. A
#: quantisation under 4 bits was not measured, and gets no estimate.
DECODE_EFFICIENCY: Mapping[str, float] = {"8bit": 0.75, "4bit": 0.60}
HIGH_BANDWIDTH_GBPS = 800.0
HIGH_BANDWIDTH_EFFICIENCY = 0.45

#: Quantisation names, by the efficiency class they decode at. Matched on the
#: name's start, case-insensitively: ``Q4_K_M`` is ``q4``, ``IQ4_XS`` is ``iq4``.
QUANT_CLASSES: Mapping[str, tuple[str, ...]] = {
    "8bit": ("f32", "f16", "bf16", "q8"),
    "4bit": ("q4", "iq4", "mxfp4", "q5", "q6"),
}


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

    def says(self, unit: str) -> str:
        """``<value> <unit> (<figure>: <basis>)``, flagged when unverified."""
        flag = "" if self.verified else ", from an unverified table row"
        return f"{self.value:.1f} {unit} ({self.figure}: {self.basis}{flag})"


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


def usable_unified_mb(
    memsize_mb: int,
    wired_limit_mb: int | None = None,
    *,
    working_set_mb: int | None = None,
) -> Figure:
    """The memory a Mac's GPU may use, in MB.

    A ``working_set_mb`` that llama.cpp logged (Metal's
    ``recommendedMaxWorkingSetSize``) is a reading. Otherwise it is an estimate:
    the kernel's wired limit when one is set (``iogpu.wired_limit_mb`` > 0, held
    to the memory), else :data:`UNIFIED_SHARE` of the memory.
    """
    if working_set_mb:
        return Figure(
            float(working_set_mb),
            READING,
            "recommendedMaxWorkingSetSize llama.cpp logged",
        )
    if wired_limit_mb:
        return Figure(
            float(min(wired_limit_mb, memsize_mb)), ESTIMATE, "iogpu.wired_limit_mb"
        )
    return Figure(
        float(int(memsize_mb * UNIFIED_SHARE)),
        ESTIMATE,
        f"{UNIFIED_SHARE:g} of memory, no wired limit set",
    )


def quant_class(quant: str) -> str | None:
    """The efficiency class of a quantisation name, None when it has none."""
    name = quant.strip().lower()
    for klass, prefixes in QUANT_CLASSES.items():
        if name.startswith(prefixes):
            return klass
    return None


def efficiency(bandwidth_gbps: float, quant: str) -> float | None:
    """The decode efficiency for this bandwidth and quantisation, None when unknown."""
    klass = quant_class(quant)
    if klass is None:
        return None
    eff = DECODE_EFFICIENCY[klass]
    if bandwidth_gbps >= HIGH_BANDWIDTH_GBPS:
        eff = min(eff, HIGH_BANDWIDTH_EFFICIENCY)
    return eff


def decode_tps(
    bandwidth_gbps: float,
    model_bytes: int,
    quant: str,
    *,
    verified: bool = True,
    device: str = "",
) -> Figure | NoEstimate:
    """Estimated decode tokens per second of a dense model on one device.

    ``efficiency x bandwidth_gbps / (model_bytes / 1e9)``: each token reads every
    weight once, at the share of the bandwidth :data:`DECODE_EFFICIENCY` states
    for the quantisation. A quantisation with no efficiency class, or a
    non-positive size or bandwidth, gets no estimate.
    """
    if bandwidth_gbps <= 0 or model_bytes <= 0:
        return NoEstimate("no bandwidth or model size to estimate decode from")
    eff = efficiency(bandwidth_gbps, quant)
    if eff is None:
        return NoEstimate(
            f"no decode estimate for quantisation {quant!r}: the rule was fitted "
            "to 16-, 8- and 4-bit weights"
        )
    on = f"{device}, " if device else ""
    gb = model_bytes / BYTES_PER_GB
    return Figure(
        eff * bandwidth_gbps / gb,
        ESTIMATE,
        f"{on}{bandwidth_gbps:g} GB/s x {eff:g} over {gb:.2f} GB read per token",
        verified=verified,
    )


def prefer(reading: float | None, estimate: Figure | NoEstimate) -> Figure | NoEstimate:
    """The machine's own reading when there is one, else the estimate."""
    if reading is not None and reading > 0:
        return Figure(float(reading), READING, "measured on this machine")
    return estimate


def classes_path() -> Path:
    """Where the shipped table is: the package's copy, else the checkout's."""
    found = shipped_file(CLASSES_FILENAME)
    if found is None:
        raise HardwareClassesError(f"{CLASSES_FILENAME} not found")
    return found


_TOP_KEYS = frozenset({"_doc", "schema", "classes", "_sources"})
_ROW_KEYS = frozenset(
    {
        "id",
        "vendor",
        "name",
        "bandwidth_gbps",
        "verified",
        "source",
        "gpu_cores",
        "memory_gb",
        "memory_gb_kind",
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
    if not isinstance(source, dict) or not str(source.get("url", "")).startswith(
        "https://"
    ):
        raise HardwareClassesError(
            f"{where}: row {rid!r} has no https source in _sources"
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
    if not isinstance(raw, dict) or raw.get("schema") != CLASSES_SCHEMA:
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
def _shipped() -> tuple[HardwareClass, ...]:
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


def match(
    name: str,
    *,
    vram_mib: int | None = None,
    gpu_cores: int | None = None,
    memory_mib: int | None = None,
    classes: tuple[HardwareClass, ...] | None = None,
) -> HardwareClass | NoEstimate:
    """The class of a device: by its name, then by what tells its variants apart.

    The name is matched whole, without vendor words (:func:`class_name`), so
    ``RTX 4060 Ti`` never matches ``RTX 4060``, nor ``RTX 4090 Laptop GPU``
    ``RTX 4090``. Rows of one name that state ``vram_gb`` are told apart by
    the card's memory in whole GB, and a card whose memory is unread or
    matches none gets no class. Rows that state GPU cores are told apart by
    the cores, and rows that state ``match_memory_gb`` by the machine's
    memory, when those are read; when more than one row is left, the one with
    the lowest bandwidth answers, so an unread variant is never estimated
    fast. A name no row has gets no class.
    """
    table = classes if classes is not None else _shipped()
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
    return min(rows, key=lambda one: one.bandwidth_gbps)


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
    classes: tuple[HardwareClass, ...] | None = None,
) -> Figure | NoEstimate:
    """A model's decode speed on a named device: the machine's reading when there
    is one, else the estimate from the device's class, else why there is none."""
    if reading is not None and reading > 0:
        return prefer(reading, NoEstimate(""))
    found = match(
        name,
        vram_mib=vram_mib,
        gpu_cores=gpu_cores,
        memory_mib=memory_mib,
        classes=classes,
    )
    if isinstance(found, NoEstimate):
        return found
    if not quant:
        return NoEstimate(
            f"{name}: the model's quantisation is unknown, so no estimate"
        )
    return decode_tps(
        found.bandwidth_gbps,
        model_bytes,
        quant,
        verified=found.verified,
        device=f"class {found.id}",
    )


def decode_readings(folder: Path | None = None) -> dict[tuple[str, str], float]:
    """Measured warm decode speeds, by (host, model), from the live fleet's lock.

    A unit's approved ``warm_decode_tok_s`` in any of the lock's rig records is a
    reading for the model the fleet's ``fleet.yaml`` names for the unit, at the
    host of the unit's address. Where one model at one host was measured more
    than once, the slowest answers. No live fleet, or one that cannot be read,
    gives no readings.
    """
    from urllib.parse import urlsplit

    from mcgyvr.fleet.files import FleetFileError, load_fleet
    from mcgyvr.fleet.roots import LOCK_DIR, LiveFleetError, live_fleet_dir

    try:
        where = folder if folder is not None else live_fleet_dir()
    except LiveFleetError:
        return {}
    if where is None:
        return {}
    try:
        fleet = load_fleet((where / "fleet.yaml").read_text(encoding="utf-8"))
    except (OSError, FleetFileError):
        return {}
    units = fleet.get("units") or {}
    found: dict[tuple[str, str], float] = {}
    for record in sorted((where / LOCK_DIR / "rigs").glob("*/*.json")):
        try:
            approved = json.loads(record.read_text(encoding="utf-8"))["approved"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if not isinstance(approved, dict):
            continue
        for unit_name, entry in approved.items():
            unit = units.get(unit_name)
            warm = entry.get("warm_decode_tok_s") if isinstance(entry, dict) else None
            if not isinstance(unit, dict) or isinstance(warm, bool):
                continue
            if not isinstance(warm, int | float) or warm <= 0:
                continue
            model = unit.get("model")
            host = urlsplit(str(unit.get("address") or "")).hostname
            if not isinstance(model, str) or not model or not host:
                continue
            key = (host, model)
            found[key] = min(found.get(key, float(warm)), float(warm))
    return found
