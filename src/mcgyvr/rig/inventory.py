""

from __future__ import annotations

import math
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcgyvr.rig import pooled, protocol
from mcgyvr.serving import ggufscan

#
MAX_DEPTH = 4
#
_SPLIT_FIRST = "-00001-of-"

#
_KV_TYPES = {"f16": 1, "q8_0": 8}

Scan = Callable[[str], Mapping[str, Any]]


@dataclass(frozen=True, kw_only=True)
class Inventory:
    ""

    folder: Path | None
    models: tuple[protocol.ModelInfo, ...] = ()
    files: Mapping[str, str] = field(default_factory=dict)
    notes: tuple[str, ...] = ()


def kv_bytes_per_token(row: Mapping[str, Any], kv_type: str) -> int | None:
    ""
    layers = row.get("kv_layers")
    if not isinstance(layers, list) or not layers:
        return None
    elements = 0
    for layer in layers:
        if not isinstance(layer, dict):
            return None
        k, v = layer.get("k_elems"), layer.get("v_elems")
        if type(k) is not int or type(v) is not int:
            return None
        elements += k + v
    block_elements, block_bytes = ggufscan.T[_KV_TYPES[kv_type]]
    total = math.ceil(elements * block_bytes / block_elements)
    return total if 1 <= total <= protocol.MAX_KV_BYTES_PER_TOKEN else None


def tensor_bytes(row: Mapping[str, Any]) -> tuple[int | None, int | None]:
    ""
    embd, output = row.get("token_embd_bytes"), row.get("output_bytes")
    if type(embd) is not int or not 1 <= embd <= protocol.MAX_MODEL_BYTES:
        return None, None
    if output is None:
        return embd, 0
    if type(output) is not int or not 1 <= output <= protocol.MAX_MODEL_BYTES:
        return None, None
    return embd, output


def _count(row: Mapping[str, Any], key: str, high: int) -> int | None:
    value = row.get(key)
    return value if type(value) is int and 1 <= value <= high else None


def describe(name: str, size: int, row: Mapping[str, Any]) -> protocol.ModelInfo:
    ""
    if "error" in row:
        return protocol.ModelInfo(name=name, size_bytes=size)
    arch = row.get("arch")
    embd_bytes, output_bytes = tensor_bytes(row)
    return protocol.ModelInfo(
        name=name,
        size_bytes=size,
        arch=arch
        if isinstance(arch, str) and protocol.SHORT_TAG.fullmatch(arch)
        else None,
        n_layers=_count(row, "n_layer", protocol.MAX_LAYERS),
        n_ctx_train=_count(row, "n_ctx_train", protocol.MAX_COUNT),
        n_embd=_count(row, "n_embd", protocol.MAX_COUNT),
        n_head_kv=_count(row, "n_head_kv", protocol.MAX_COUNT),
        kv_bytes_per_token=kv_bytes_per_token(row, pooled.KV_CACHE_TYPE),
        embd_bytes=embd_bytes,
        output_bytes=output_bytes,
    )


def _candidates(folder: Path) -> list[Path]:
    found: list[Path] = []
    base = len(folder.parts)
    for root, dirs, files in os.walk(folder, followlinks=False):
        here = Path(root)
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        if len(here.parts) - base >= MAX_DEPTH:
            dirs[:] = []
        for name in sorted(files):
            if name.startswith(".") or not name.lower().endswith(".gguf"):
                continue
            if "-of-" in name and _SPLIT_FIRST not in name:
                continue
            found.append(here / name)
    return found


_SCANNED: dict[tuple[str, int, int], Mapping[str, Any]] = {}


def _scan_cached(path: Path, size: int, mtime_ns: int, scan: Scan) -> Mapping[str, Any]:
    key = (str(path), size, mtime_ns)
    if key not in _SCANNED:
        try:
            _SCANNED[key] = scan(str(path))
        except Exception as exc:  #
            _SCANNED[key] = {"error": exc.__class__.__name__}
    return _SCANNED[key]


def read(folder: str | None, *, scan: Scan = ggufscan.scan) -> Inventory:
    ""
    if folder is None:
        return Inventory(folder=None)
    root = Path(folder)
    try:
        resolved_root = root.resolve(strict=True)
    except OSError:
        return Inventory(folder=root, notes=(f"{folder}: not a folder this reads",))
    if not resolved_root.is_dir():
        return Inventory(folder=root, notes=(f"{folder}: not a folder",))
    models: list[protocol.ModelInfo] = []
    files: dict[str, str] = {}
    notes: list[str] = []
    for candidate in _candidates(resolved_root):
        name = candidate.name
        relative = candidate.relative_to(resolved_root).as_posix()
        try:
            real = candidate.resolve(strict=True)
            stat = real.stat()
        except OSError:
            continue
        if not real.is_relative_to(resolved_root) or not real.is_file():
            notes.append(f"{relative}: leaves the models folder; not named")
            continue
        if not protocol.MODEL_NAME.fullmatch(name):
            notes.append(f"{relative}: a name the hub's protocol cannot carry")
            continue
        if name in files:
            notes.append(f"{relative}: a second file named {name}; not named")
            continue
        if len(models) >= protocol.MAX_MODELS:
            notes.append(f"more than {protocol.MAX_MODELS} models; the rest not named")
            break
        if not 1 <= stat.st_size <= protocol.MAX_MODEL_BYTES:
            continue
        row = _scan_cached(real, stat.st_size, stat.st_mtime_ns, scan)
        models.append(describe(name, stat.st_size, row))
        files[name] = real.relative_to(resolved_root).as_posix()
    return Inventory(
        folder=resolved_root, models=tuple(models), files=files, notes=tuple(notes)
    )


def resolve(inventory: Inventory, name: str) -> str | None:
    ""
    return inventory.files.get(name)
