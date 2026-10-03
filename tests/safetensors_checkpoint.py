"""Tiny invented safetensors checkpoints for the scanner's tests.

A checkpoint built here is a directory holding one or more ``*.safetensors``
files and a ``config.json``. Each file is a real safetensors layout (the
eight-byte little-endian header length, the JSON header, then the data), with
zero bytes for data and shapes of a few elements, so nothing here weighs
anything and no model of any real family is copied: the names are invented.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

#: name -> (dtype, shape)
Spec = dict[str, tuple[str, list[int]]]

#: Bytes per element of the dtypes the tests build, from the safetensors
#: specification; the scanner's own table is what is under test, so it is not
#: imported.
WIDTH = {"F32": 4, "F16": 2, "BF16": 2, "I32": 4, "I8": 1, "F8_E4M3": 1}


def elems(shape: list[int]) -> int:
    n = 1
    for d in shape:
        n *= d
    return n


def nbytes(dtype: str, shape: list[int]) -> int:
    """Bytes of one tensor, by the specification's widths."""
    return elems(shape) * WIDTH[dtype]


def write_shard(
    path: Path,
    spec: Spec,
    *,
    widths: dict[str, int] | None = None,
    claim: dict[str, tuple[str, list[int]]] | None = None,
) -> None:
    """Write one shard holding ``spec``.

    ``widths`` adds or overrides bytes per element used to lay the data out,
    and ``claim`` the dtype and shape the header states for a tensor, so a test
    can build a file whose header disagrees with its own offsets.
    """
    wide = {**WIDTH, **(widths or {})}
    header: dict[str, Any] = {"__metadata__": {"format": "pt"}}
    begin = 0
    for name, (dtype, shape) in spec.items():
        size = elems(shape) * wide[dtype]
        stated_dtype, stated_shape = (claim or {}).get(name, (dtype, shape))
        header[name] = {
            "dtype": stated_dtype,
            "shape": stated_shape,
            "data_offsets": [begin, begin + size],
        }
        begin += size
    raw = json.dumps(header).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + bytes(begin))


def write_config(directory: Path, config: dict[str, Any]) -> None:
    (directory / "config.json").write_text(json.dumps(config), encoding="utf-8")


def decoder_spec(n_layer: int, *, hidden: int = 8, ffn: int = 16) -> Spec:
    """Tensors of an invented decoder: embedding, blocks, final norm, head."""
    spec: Spec = {"model.embed_tokens.weight": ("BF16", [32, hidden])}
    for i in range(n_layer):
        p = f"model.layers.{i}"
        spec[f"{p}.self_attn.q_proj.weight"] = ("BF16", [hidden, hidden])
        spec[f"{p}.mlp.up_proj.weight"] = ("BF16", [ffn, hidden])
        spec[f"{p}.input_layernorm.weight"] = ("BF16", [hidden])
    spec["model.norm.weight"] = ("BF16", [hidden])
    spec["lm_head.weight"] = ("BF16", [32, hidden])
    return spec


def base_config(**over: Any) -> dict[str, Any]:
    """A config for ``decoder_spec(2)`` of an invented architecture."""
    cfg: dict[str, Any] = {
        "model_type": "example-decoder",
        "num_hidden_layers": 2,
        "hidden_size": 8,
        "num_attention_heads": 4,
        "num_key_value_heads": 2,
        "torch_dtype": "bfloat16",
    }
    cfg.update(over)
    return cfg


def make(directory: Path, spec: Spec, config: dict[str, Any]) -> Path:
    """One-file checkpoint of ``spec`` with ``config`` in ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    write_shard(directory / "model.safetensors", spec)
    write_config(directory, config)
    return directory
