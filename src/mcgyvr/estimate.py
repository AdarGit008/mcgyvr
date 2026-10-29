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
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from mcgyvr.hubwire import BYTES_PER_DECIMAL_GB as BYTES_PER_DECIMAL_GB
from mcgyvr.hubwire import DECODE_EFFICIENCY as DECODE_EFFICIENCY
from mcgyvr.hubwire import FIGURE_ESTIMATE as ESTIMATE
from mcgyvr.hubwire import FIGURE_KINDS, decode_efficiency
from mcgyvr.hubwire import FIGURE_READING as READING
from mcgyvr.hubwire import FITTED_ON as FITTED_ON
from mcgyvr.hubwire import HIGH_BANDWIDTH_EFFICIENCY as HIGH_BANDWIDTH_EFFICIENCY
from mcgyvr.hubwire import HIGH_BANDWIDTH_GBPS as HIGH_BANDWIDTH_GBPS
from mcgyvr.shipped import shipped_file

CLASSES_FILENAME = "hardware-classes.json"

#: The decode efficiency for a bandwidth, quantisation and vendor: the wire's.
efficiency = decode_efficiency

#: The version of the table's format this code reads.
CLASSES_SCHEMA = 1

#: The share of a Mac's memory its GPU may wire when the kernel's own limit is in
#: force (``iogpu.wired_limit_mb`` is 0): llama.cpp treats Metal's
#: ``recommendedMaxWorkingSetSize`` as the device's total, and a 192 GB machine
#: logs 75.1% of its memory there
#: (https://github.com/ggml-org/llama.cpp/discussions/9784); the exact kernel
#: rule has no Apple source, so this share is an estimate. The machine reader
#: (``serving/rigscan.py`` ``UNIFIED_SHARE``, standalone) spells the same value.
UNIFIED_SHARE = 0.75


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


def decode_tps(
    bandwidth_gbps: float,
    model_bytes: int,
    quant: str,
    *,
    verified: bool = True,
    device: str = "",
    vendor: str = FITTED_ON,
) -> Figure | NoEstimate:
    """Estimated decode tokens per second of a dense model on one device.

    ``efficiency x bandwidth_gbps / (model_bytes / 1e9)``: each token reads every
    weight once, at the share of the bandwidth :data:`DECODE_EFFICIENCY` states
    for the quantisation. A quantisation with no efficiency class, or a
    non-positive size or bandwidth, gets no estimate.
    """
    if bandwidth_gbps <= 0 or model_bytes <= 0:
        return NoEstimate("no bandwidth or model size to estimate decode from")
    eff = efficiency(bandwidth_gbps, quant, vendor=vendor)
    if eff is None:
        return NoEstimate(
            f"no decode estimate for quantisation {quant!r}: the rule was fitted "
            "to 16-, 8- and 4- to 6-bit weights"
        )
    on = f"{device}, " if device else ""
    fitted = "" if vendor == FITTED_ON else ", shares fitted on Apple silicon"
    gb = model_bytes / BYTES_PER_DECIMAL_GB
    return Figure(
        eff * bandwidth_gbps / gb,
        ESTIMATE,
        f"{on}{bandwidth_gbps:g} GB/s x {eff:g} over {gb:.2f} GB read per "
        f"token{fitted}",
        verified=verified,
    )


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
