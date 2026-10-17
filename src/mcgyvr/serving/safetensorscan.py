#
""

from __future__ import annotations

import json
import os
import struct
import sys
from typing import Any

#
#
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

#
_FULL = "full_attention"
_SLIDING = "sliding_attention"

#
_LENGTH_FIELD = struct.calcsize("<Q")


class Refused(ValueError):  #
    ""


def dtype_size(dtype: str) -> int:
    ""
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
    ""
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
    ""
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
    ""
    parts = name.split(".")
    for i in range(len(parts) - 1):
        if parts[i] == "layers" and parts[i + 1].isdigit():
            return int(parts[i + 1])
    return None


#
#
#
_TOWER_STARTS = ("vision", "visual", "audio", "image")
_TOWER_PARTS = frozenset(
    {"multi_modal_projector", "mm_projector", "embed_vision", "embed_audio"}
)


def _in_tower(name: str) -> bool:
    ""
    return any(
        part.startswith(_TOWER_STARTS) or part in _TOWER_PARTS
        for part in name.split(".")
    )


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
    ""
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
    total = bytes_input = bytes_output = bytes_output_matrix = bytes_tower = 0
    has_head = False
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
            if _in_tower(name):
                bytes_tower += n
                continue
            if name.split(".")[0] == "lm_head":
                has_head = True
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
    tie_key = "tie_word_embeddings"
    tie_stated = cfg.get(tie_key) if tie_key in cfg else root.get(tie_key)
    tied = tie_stated is True or not has_head

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
        "bytes_tower": bytes_tower,
        "tied_embeddings": tied,
        "dtype_bytes": by_dtype,
        "kv_layers": _kv_layers(cfg, n_layer, n_head_kv, head_dim),
        "sliding_window": cfg.get("sliding_window"),
        "quantization_config": quant,
        "recurrent_blocks": [],
        "n_recurrent": 0,
        "dtype": dtype_stated,
    }


def scan(path: str) -> dict[str, Any]:
    ""
    try:
        return _scan(path)
    except (Refused, OSError, struct.error) as e:
        return {"file": path, "error": str(e) or repr(e)}


#
#
if __name__ == "__main__":
    print(json.dumps([scan(d) for d in sys.argv[1:]]))
