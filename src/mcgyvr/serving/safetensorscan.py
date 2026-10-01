#!/usr/bin/env python3
"""Read a safetensors checkpoint's tensor table and its ``config.json``.

This is the vLLM counterpart of :mod:`mcgyvr.serving.ggufscan`, and it keeps
that module's one rule: **bits-per-weight is a guess; the tensor table is
not**. A checkpoint directory is read
header by header -- the first eight bytes of a ``.safetensors`` file say how
long its JSON header is, and the header says every tensor's dtype, shape and
byte range -- and never a weight. What the sharding sizer reads from the one
row it returns is therefore a sum of tensor bytes by where they sit (a decoder
block, the input embedding, the rest), not a file size divided by a guess, and
not a parameter count times a bit width somebody assumed for a quantised
checkpoint (a packed AWQ/GPTQ ``qweight`` is an integer tensor whose element
count says nothing about parameters).

**It is stdlib-only and self-contained, for the same reason ggufscan is.**
Operators run ``python -m mcgyvr.serving.safetensorscan <model dir>`` on the
machine that holds the weights, and a gate may ship the file to that machine
as bytes and run it as ``python3 -``, where there is no venv, no ``mcgyvr`` and
no ``PYTHONPATH``. An import added here fails on that machine and nowhere
else, so ``tests/test_the_safetensors_scanner_needs_nothing_a_rig_lacks.py``
refuses one.

**A dtype it does not know is refused by name, never sized as the widest one.**
Every tensor's ``data_offsets`` span is also compared with the bytes its dtype
and shape imply, so a wrong entry in the dtype table cannot pass quietly: it
disagrees with the file's own bookkeeping and the row is refused. A shard whose
header promises more bytes than the file holds (a truncated download) is
refused the same way.

How the row is read from ``config.json``. Multimodal checkpoints nest the
language model's fields under ``text_config``; when the top level has one,
every geometry field, the architecture (``model_type``) and the sliding-window
fields are read from it, because the decoder blocks counted here are that
model's. ``quantization_config`` and ``dtype`` are taken from the top level
first and from ``text_config`` only when the top level states none. A missing
``num_key_value_heads`` means ``num_attention_heads`` -- that default is the
Hugging Face config's own convention (multi-head attention), stated here and
not invented. A refusal of a row is ``{"file": ..., "error": ...}``, as
ggufscan's is.
"""

from __future__ import annotations

import json
import os
import struct
import sys
from typing import Any

#: Bytes per element of every dtype a safetensors header may name. A name not
#: here (and not an ``F8_*`` variant, see :func:`dtype_size`) is refused.
_DTYPE_BYTES: dict[str, int] = {
    "F64": 8,
    "F32": 4,
    "F16": 2,
    "BF16": 2,
    "I64": 8,
    "I32": 4,
    "I16": 2,
    "I8": 1,
    "U8": 1,
    "BOOL": 1,
    "U16": 2,
    "U32": 4,
    "U64": 8,
    "F8_E4M3": 1,
    "F8_E5M2": 1,
}

#: The two per-layer attention kinds a ``layer_types`` list may state.
_FULL = "full_attention"
_SLIDING = "sliding_attention"

#: The length of the little-endian u64 that opens a safetensors file.
_LENGTH_FIELD = struct.calcsize("<Q")


class Refused(ValueError):  # noqa: N818 - a refusal, named as one
    """The checkpoint cannot be read honestly; the message says why and what to do."""


def dtype_size(dtype: str) -> int:
    """Bytes per element of ``dtype``, or a refusal naming it.

    Any ``F8_*`` variant is one byte: the family is defined by its width, and a
    new member of it (a scale-only ``F8_E8M0``) does not change that. Every
    other dtype is looked up and never assumed, because a guessed width turns a
    quantised checkpoint into several times its size or a fraction of it.
    """
    if dtype in _DTYPE_BYTES:
        return _DTYPE_BYTES[dtype]
    if dtype.startswith("F8_"):
        return _DTYPE_BYTES["I8"]
    raise Refused(
        f"unknown safetensors dtype {dtype!r}: this scanner sizes only "
        f"{sorted(_DTYPE_BYTES)} and F8_* variants and will not guess a width; "
        "add the dtype to _DTYPE_BYTES with its size from the safetensors "
        "specification"
    )


def _read_header(path: str) -> tuple[dict[str, Any], int]:
    """One shard's tensor table, and the size of its data region.

    Reads the eight length bytes and the JSON header, never past them. The
    data region size is returned so a tensor claiming bytes the file does not
    hold is caught by the caller.
    """
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(_LENGTH_FIELD)
        if len(head) != _LENGTH_FIELD:
            raise Refused(f"{path}: shorter than the safetensors length field")
        (n,) = struct.unpack("<Q", head)
        if n > size - _LENGTH_FIELD:
            raise Refused(
                f"{path}: header claims {n} bytes but the file holds "
                f"{size - _LENGTH_FIELD} after the length field; not a safetensors "
                "file, or a truncated one"
            )
        raw = f.read(n)
    try:
        table = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise Refused(f"{path}: the header is not JSON: {e}") from e
    if not isinstance(table, dict):
        raise Refused(f"{path}: the header is not a JSON object")
    return table, size - _LENGTH_FIELD - n


def _tensors(path: str) -> list[tuple[str, str, list[int], int]]:
    """Every tensor of one shard as (name, dtype, shape, bytes), cross-checked.

    The bytes are ``prod(shape) * dtype size``, and must equal the span the
    header itself gives (``end - begin``) and fit in the file. A mismatch is
    refused rather than resolved: it means the dtype table is wrong for this
    file, and any sum built on it would be wrong with nothing saying so.
    """
    table, data_size = _read_header(path)
    out: list[tuple[str, str, list[int], int]] = []
    for name, entry in table.items():
        if name == "__metadata__":
            continue
        if not isinstance(entry, dict):
            raise Refused(f"{path}: tensor {name!r} has no dtype/shape/data_offsets")
        dtype = entry.get("dtype")
        shape = entry.get("shape")
        offsets = entry.get("data_offsets")
        if not isinstance(dtype, str):
            raise Refused(f"{path}: tensor {name!r} states no dtype")
        if not isinstance(shape, list) or not all(
            isinstance(d, int) and not isinstance(d, bool) and d >= 0 for d in shape
        ):
            raise Refused(f"{path}: tensor {name!r} states no valid shape")
        if (
            not isinstance(offsets, list)
            or len(offsets) != 2
            or not all(isinstance(o, int) and not isinstance(o, bool) for o in offsets)
        ):
            raise Refused(f"{path}: tensor {name!r} states no valid data_offsets")
        n = dtype_size(dtype)
        for d in shape:
            n *= d
        begin, end = offsets
        if end - begin != n:
            raise Refused(
                f"{path}: tensor {name!r} is {dtype} {shape}, which is {n} bytes, "
                f"but its data_offsets span {end - begin}; the dtype table "
                "disagrees with the file, so no sum is trusted"
            )
        if begin < 0 or end > data_size:
            raise Refused(
                f"{path}: tensor {name!r} ends at {end} but the data region "
                f"holds {data_size}; the file is truncated"
            )
        out.append((name, dtype, shape, n))
    return out


def _block_of(name: str) -> int | None:
    """The decoder block a tensor sits in: the integer after a ``layers`` part.

    ``model.layers.12.self_attn.q_proj.qweight`` and
    ``model.language_model.layers.12.mlp.gate_proj.weight`` are both block 12.
    The first ``layers.<integer>`` pair in the name is the block.
    """
    parts = name.split(".")
    for i in range(len(parts) - 1):
        if parts[i] == "layers" and parts[i + 1].isdigit():
            return int(parts[i + 1])
    return None


def _config(directory: str) -> dict[str, Any]:
    path = os.path.join(directory, "config.json")
    if not os.path.isfile(path):
        raise Refused(
            f"{directory}: no config.json; the layer count, widths and head "
            "counts are read from it, copy it beside the weights"
        )
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise Refused(f"{path}: not JSON: {e}") from e
    if not isinstance(cfg, dict):
        raise Refused(f"{path}: not a JSON object")
    return cfg


def _positive(cfg: dict[str, Any], key: str) -> int:
    value = cfg.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise Refused(
            f"config.json states no usable {key} (got {value!r}); it is read "
            "from the config and not guessed, so add it there"
        )
    return value


def _kv_layers(
    cfg: dict[str, Any], n_layer: int, heads: int, head_dim: int
) -> list[dict[str, Any]]:
    """One row per layer that caches, each stating its own width.

    Whether a layer slides is read from ``layer_types`` when the config has it.
    A declared ``sliding_window`` (not switched off by ``use_sliding_window:
    false``) with no per-layer list is UNKNOWN, not alternating and not "all":
    ggufscan documents why an assumed split is wrong (the assignment, not just
    the count, can set the total), and the sizer refuses a row whose layers
    say ``None``. A config that declares no window at all has no sliding layer.
    """
    types = cfg.get("layer_types")
    if types is not None:
        if not isinstance(types, list) or len(types) != n_layer:
            raise Refused(
                f"config.json layer_types must list one type for each of the "
                f"{n_layer} layers (got {types!r})"
            )
        other = sorted({str(t) for t in types} - {_FULL, _SLIDING})
        if other:
            raise Refused(
                f"config.json layer_types names {other}, which this scanner "
                f"does not size (it reads only {_FULL} and {_SLIDING}); "
                "recurrent and other layer kinds are refused rather than guessed"
            )
    window = cfg.get("sliding_window")
    declared = bool(window) and cfg.get("use_sliding_window") is not False
    rows: list[dict[str, Any]] = []
    for layer in range(n_layer):
        swa: bool | None
        if types is not None:
            swa = types[layer] == _SLIDING
        elif declared:
            swa = None
        else:
            swa = False
        rows.append(
            {
                "layer": layer,
                "is_swa": swa,
                "k_elems": heads * head_dim,
                "v_elems": heads * head_dim,
                "heads": heads,
            }
        )
    return rows


def _scan(directory: str) -> dict[str, Any]:
    if not os.path.isdir(directory):
        raise Refused(f"{directory}: not a directory; give the model directory")
    shards = sorted(
        os.path.join(directory, n)
        for n in os.listdir(directory)
        if n.endswith(".safetensors")
    )
    if not shards:
        raise Refused(f"{directory}: no *.safetensors files")
    root = _config(directory)
    inner = root.get("text_config")
    cfg: dict[str, Any] = inner if isinstance(inner, dict) else root

    n_layer = _positive(cfg, "num_hidden_layers")
    n_embd = _positive(cfg, "hidden_size")
    n_head = _positive(cfg, "num_attention_heads")
    n_head_kv = (
        _positive(cfg, "num_key_value_heads")
        if cfg.get("num_key_value_heads") is not None
        else n_head
    )
    if cfg.get("head_dim") is not None:
        head_dim = _positive(cfg, "head_dim")
    elif n_embd % n_head == 0:
        head_dim = n_embd // n_head
    else:
        raise Refused(
            f"config.json hidden_size {n_embd} is not a multiple of "
            f"num_attention_heads {n_head} and states no head_dim; the cache "
            "width is not guessed, so add head_dim to the config"
        )
    if cfg.get("kv_lora_rank") is not None:
        raise Refused(
            "config.json declares kv_lora_rank (a latent-compressed attention "
            "cache); this scanner sizes heads x head_dim and will not state a "
            "cache width for a layout it does not model"
        )

    seen: dict[str, str] = {}
    by_block: dict[int, int] = {}
    matrix_by_block: dict[int, int] = {}
    total = bytes_input = bytes_output = bytes_output_matrix = 0
    by_dtype: dict[str, int] = {}
    for shard in shards:
        for name, dtype, shape, n in _tensors(shard):
            if name in seen:
                raise Refused(
                    f"tensor {name!r} is in both {seen[name]} and {shard}; a "
                    "sum would count it twice"
                )
            seen[name] = shard
            total += n
            by_dtype[dtype] = by_dtype.get(dtype, 0) + n
            block = _block_of(name)
            if block is not None:
                by_block[block] = by_block.get(block, 0) + n
                if len(shape) >= 2:
                    matrix_by_block[block] = matrix_by_block.get(block, 0) + n
            elif "embed_tokens" in name:
                bytes_input += n
            else:
                bytes_output += n
                if len(shape) >= 2:
                    bytes_output_matrix += n
    blocks = sorted(by_block)

    quant = root.get("quantization_config")
    if quant is None:
        quant = cfg.get("quantization_config")
    dtype_stated = next(
        (c[k] for c in (root, cfg) for k in ("torch_dtype", "dtype") if k in c), None
    )
    return {
        "file": directory,
        "size_bytes": sum(os.path.getsize(s) for s in shards),
        "arch": cfg.get("model_type"),
        "n_layer": n_layer,
        "n_embd": n_embd,
        "n_head": n_head,
        "n_head_kv": n_head_kv,
        "head_dim": head_dim,
        "bytes_total_tensors": total,
        "bytes_by_block": {str(b): by_block[b] for b in blocks},
        "bytes_matrix_by_block": {str(b): matrix_by_block.get(b, 0) for b in blocks},
        "bytes_input": bytes_input,
        "bytes_output": bytes_output,
        "bytes_output_matrix": bytes_output_matrix,
        "dtype_bytes": by_dtype,
        "kv_layers": _kv_layers(cfg, n_layer, n_head_kv, head_dim),
        "sliding_window": cfg.get("sliding_window"),
        "quantization_config": quant,
        "recurrent_blocks": [],
        "n_recurrent": 0,
        "dtype": dtype_stated,
    }


def scan(path: str) -> dict[str, Any]:
    """Read the checkpoint directory ``path``: one row, or ``{"file", "error"}``.

    A directory this scanner refuses (an unknown dtype, a dtype that
    disagrees with the offsets, a config missing a field, a layer kind it does
    not size) comes back as an error row naming why, as ggufscan's does, so a
    caller reading rows from JSON and one calling in-process see the same
    thing and neither gets a number the file did not state.
    """
    try:
        return _scan(path)
    except (Refused, OSError, struct.error) as e:
        return {"file": path, "error": str(e) or repr(e)}


# Guarded, as ggufscan's is: a gate may import this module to locate it, and an
# unguarded loop would print "[]" on every such import.
if __name__ == "__main__":
    print(json.dumps([scan(d) for d in sys.argv[1:]]))
