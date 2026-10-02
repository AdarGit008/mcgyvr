"""The models a rig can serve, named for the hub and never addressed by path.

The hub names a model; the agent finds it in its own inventory. So a hello
says of each model file under the owner's models folder its *name* (the
file's own name, which carries no folder), its size, and what planning reads
from its header — the architecture, layer count, trained context, embedding
width, KV heads, and the KV cache's bytes per token of context at the KV type
the head runs with, and the sizes of its token embedding and output tensors
— read by the product's own GGUF reader
(:func:`mcgyvr.serving.ggufscan.scan`), never guessed from the size.

A head is started only on a model this inventory holds (:func:`resolve`): the
name is looked up, never joined to a path, so no name the hub sends can
reach a file outside the folder. A file is held only when it lies under the
folder once its links are resolved, is a regular file, and its name is one
the protocol carries; of a split model only its first part is named. Two
files of one name keep the first (by path) and say so. A header that does not
read leaves its counts unsaid, not guessed.
"""

from __future__ import annotations

import math
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcgyvr.rig import protocol
from mcgyvr.sandbox import pooled
from mcgyvr.serving import ggufscan

#: How deep under the models folder files are looked for.
MAX_DEPTH = 4
#: A split model's later parts: ``-00002-of-00003.gguf`` and on.
_SPLIT_FIRST = "-00001-of-"

#: The GGML type number of each KV cache type the head may run with.
_KV_TYPES = {"f16": 1, "q8_0": 8}

Scan = Callable[[str], Mapping[str, Any]]


@dataclass(frozen=True, kw_only=True)
class Inventory:
    """The models found, their files relative to the folder (its links
    resolved), and notes."""

    folder: Path | None
    models: tuple[protocol.ModelInfo, ...] = ()
    files: Mapping[str, str] = field(default_factory=dict)
    notes: tuple[str, ...] = ()


def kv_bytes_per_token(row: Mapping[str, Any], kv_type: str) -> int | None:
    """The KV cache's bytes per token of context of the model ``row`` reads
    (one :func:`~mcgyvr.serving.ggufscan.scan` row), at ``kv_type``; ``None``
    when the row names no caching layer."""
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
    """The token embedding's and the output tensor's bytes in ``row``: the
    output is 0 when the file has none (it reuses the embedding), and both
    are ``None`` when the file has no token embedding."""
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
    """Model ``name`` of ``size`` bytes as a hello carries it, from its row."""
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
        except Exception as exc:  # a header that does not read says nothing
            _SCANNED[key] = {"error": exc.__class__.__name__}
    return _SCANNED[key]


def read(folder: str | None, *, scan: Scan = ggufscan.scan) -> Inventory:
    """The models under ``folder``; an empty inventory when there is none."""
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
    """Model ``name``'s file, relative to the models folder, or ``None``."""
    return inventory.files.get(name)
