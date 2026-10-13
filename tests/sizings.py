"""Sizing a model from its header, and whose host memory pays for it."""

from __future__ import annotations

import json
import struct
from datetime import date
from typing import Any

from mcgyvr.knowledge import online
from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, vramfit
from tests import machine_shapes
from tests.knowledge_online import Recorded

DAY = date(2026, 10, 7)


REPO = "example-org/Invented-MoE-GGUF"


BASE = "example-org/Invented-MoE"


SHA = "a" * 40


BASE_SHA = "c" * 40


FILE = "invented-moe-Q4_K_M.gguf"


FILE_SHA256 = "b" * 64


#: What the Hub says the file weighs: far more than its header.
SIZE = 9_000_000_000


#: The header's own context, and the base model's config.json's.
HEADER_CONTEXT = 65536


CONFIG_CONTEXT = 32768


F32, F16, Q4_K = 0, 1, 12


STRING, UINT32, ARRAY = 8, 4, 9


def _string(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack("<Q", len(raw)) + raw


def _kv(key: str, value: Any) -> bytes:
    if isinstance(value, list):
        items = b"".join(_string(v) for v in value)
        return (
            _string(key)
            + struct.pack("<I", ARRAY)
            + struct.pack("<I", STRING)
            + struct.pack("<Q", len(value))
            + items
        )
    if isinstance(value, str):
        return _string(key) + struct.pack("<I", STRING) + _string(value)
    return _string(key) + struct.pack("<I", UINT32) + struct.pack("<I", value)


def _tensor(name: str, dims: tuple[int, ...], kind: int) -> bytes:
    head = _string(name) + struct.pack("<I", len(dims))
    head += b"".join(struct.pack("<Q", d) for d in dims)
    return head + struct.pack("<I", kind) + struct.pack("<Q", 0)


def invented_header() -> bytes:
    """An MoE of two expert blocks and a grafted MTP head, with a vocabulary
    long enough that the first slice read does not hold the whole header."""
    keys: dict[str, Any] = {
        "general.architecture": "invented",
        "invented.block_count": 3,
        "invented.context_length": HEADER_CONTEXT,
        "invented.embedding_length": 64,
        "invented.attention.head_count": 8,
        "invented.attention.head_count_kv": 2,
        "invented.attention.key_length": 16,
        "invented.attention.value_length": 16,
        "invented.expert_count": 4,
        "invented.expert_used_count": 2,
        "invented.nextn_predict_layers": 1,
        "tokenizer.ggml.tokens": [f"token-{i:06d}-" + "x" * 90 for i in range(30000)],
    }
    tensors: list[tuple[str, tuple[int, ...], int]] = [
        ("token_embd.weight", (64, 30000), F16),
        ("output.weight", (64, 30000), F16),
    ]
    for block in range(3):
        tensors += [
            (f"blk.{block}.attn_q.weight", (64, 64), F16),
            (f"blk.{block}.ffn_up_exps.weight", (64, 256, 4), Q4_K),
        ]
    tensors.append(("blk.2.nextn.eh_proj.weight", (128, 64), F16))
    body = b"GGUF" + struct.pack("<I", 3)
    body += struct.pack("<Q", len(tensors)) + struct.pack("<Q", len(keys))
    body += b"".join(_kv(k, v) for k, v in keys.items())
    body += b"".join(_tensor(n, d, k) for n, d, k in tensors)
    return body


def _sibling(name: str, size: int, sha256: str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"rfilename": name, "size": size}
    if sha256 is not None:
        entry["lfs"] = {"sha256": sha256, "size": size}
    return entry


def hub(header: bytes, *, base_config: bool = True) -> Recorded:
    """The invented repository, its base model and the file, as the Hub serves them."""
    api = {
        "id": REPO,
        "sha": SHA,
        "private": False,
        "gated": False,
        "cardData": {"base_model": [BASE]},
        "siblings": [
            _sibling("README.md", 10),
            _sibling(FILE, SIZE, FILE_SHA256),
            _sibling("invented-moe-Q8_0-00001-of-00002.gguf", SIZE, "d" * 64),
            _sibling("invented-moe-Q8_0-00002-of-00002.gguf", SIZE, "e" * 64),
            _sibling("mmproj-invented-F16.gguf", 1000, "f" * 64),
        ],
    }
    bodies = {
        online.api_url(REPO): json.dumps(api).encode(),
        online.resolve_url(REPO, SHA, FILE): header,
    }
    if base_config:
        bodies[online.api_url(BASE)] = json.dumps(
            {"id": BASE, "sha": BASE_SHA}
        ).encode()
        bodies[online.resolve_url(BASE, BASE_SHA, "config.json")] = json.dumps(
            {"max_position_embeddings": CONFIG_CONTEXT}
        ).encode()
    return Recorded(bodies=bodies)


#: The window every sizing here declares.
WINDOW = 4096


#: The invented model: its name, and how many expert blocks it has.
MODEL = "example-moe"


BLOCKS = 8


def machines() -> list[machine_shapes.Shape]:
    """Every invented machine whose scan reports a card."""
    return [machine for machine in machine_shapes.shapes() if machine.readable_cards]


def spilling(scan: Scan) -> ModelSpec:
    """An invented MoE that fits the roomiest card of ``scan`` only by spilling.

    Its non-expert weights and the card's scratch allowance take half of the
    card's free memory; each expert block takes a quarter of what the
    allowance leaves, so two blocks stay on the card and the rest spill to
    host memory. It caches nothing and has no recurrent state, so its slot
    count moves nothing here.
    """
    free = max(gpu.vram.free_mib for gpu in scan.gpus) << 20
    room = free - (vramfit.SCRATCH_AND_CONTEXT_MIB << 20)
    nonexpert = room // 2
    block = room // 4
    by_block = {str(index): block for index in range(BLOCKS)}
    geometry: dict[str, Any] = {
        "file": f"/models/{MODEL}.gguf",
        "size_bytes": nonexpert + block * BLOCKS,
        "arch": "invented",
        "n_layer": BLOCKS,
        "bytes_nonexpert": nonexpert,
        "bytes_experts": block * BLOCKS,
        "placeable_blocks": list(range(BLOCKS)),
        "expert_bytes_by_block": by_block,
        "kv_layers": [],
        "n_recurrent": 0,
    }
    return ModelSpec(
        name=MODEL,
        vram_gb=0.0,
        ram_gb=0.0,
        disk_gb=0.0,
        geometry=geometry,
        hf_cache="/models/hf",
        kv_cache_dtype_k="f16",
        kv_cache_dtype_v="f16",
    )
