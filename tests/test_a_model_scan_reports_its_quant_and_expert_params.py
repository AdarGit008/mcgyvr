"""A model scan reports its quant label and its expert and active params.

RED. ``ggufscan.scan`` (``src/mcgyvr/serving/ggufscan.py:64``) reports
``params_total`` and ``type_bytes`` and no quant label, no expert params and no
active params; and a vLLM model has no reader at all, only the ``vram_gb`` and
``disk_gb`` an operator declared, which is where ``Fit.ram_gb = 0.0`` for vLLM
comes from. The intent is ``records/plans/fleet-identity.md``, "model_spec_id".
"""

from __future__ import annotations

import importlib
import json
import struct
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcgyvr.serving import ggufscan
from tests.red_port.conftest import required

#: ``ggufscan`` is untyped on purpose (it ships to a rig as bytes); typed here.
SCAN: Callable[[str], dict[str, Any]] = ggufscan.scan

#: ggml type 2 and llama.cpp file type 2 are both Q4_0.
Q4_0 = 2


def _s(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack("<Q", len(raw)) + raw


def _u32(value: int) -> bytes:
    return struct.pack("<I", value)


def tiny_moe_gguf(path: Path) -> Path:
    """One block, eight experts, two used: 16,384 expert params, 2,048 others."""
    kv = [
        ("general.architecture", 8, _s("qwen2moe")),
        ("general.file_type", 4, _u32(Q4_0)),
        ("qwen2moe.block_count", 4, _u32(1)),
        ("qwen2moe.expert_count", 4, _u32(8)),
        ("qwen2moe.expert_used_count", 4, _u32(2)),
        ("qwen2moe.attention.head_count", 4, _u32(4)),
        ("qwen2moe.attention.head_count_kv", 4, _u32(2)),
        ("qwen2moe.embedding_length", 4, _u32(64)),
    ]
    tensors = [
        ("blk.0.ffn_up_exps.weight", [32, 64, 8]),
        ("blk.0.attn_q.weight", [32, 64]),
    ]
    out = b"GGUF" + struct.pack("<IQQ", 3, len(tensors), len(kv))
    for key, kind, value in kv:
        out += _s(key) + _u32(kind) + value
    for name, dims in tensors:
        out += _s(name) + _u32(len(dims))
        out += b"".join(struct.pack("<Q", d) for d in dims) + struct.pack(
            "<IQ", Q4_0, 0
        )
    path.write_bytes(out)
    return path


def test_ggufscan_reports_quant_expert_and_active_params(tmp_path: Path) -> None:
    row: dict[str, Any] = SCAN(str(tiny_moe_gguf(tmp_path / "tiny.gguf")))
    assert row.get("error") is None, row
    assert row.get("quant") == "Q4_0", "the file type is the quant label"
    assert row.get("params_experts") == 16384
    assert row.get("params_active") == 2048 + 16384 * 2 // 8


def test_hfscan_reads_a_vllm_model_s_config(tmp_path: Path) -> None:
    """Qwen2.5-Coder-7B-Instruct-AWQ's shape: 28 layers, 4 KV heads of 128."""
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "config.json").write_text(
        json.dumps(
            {
                "architectures": ["Qwen2ForCausalLM"],
                "num_hidden_layers": 28,
                "hidden_size": 3584,
                "num_attention_heads": 28,
                "num_key_value_heads": 4,
                "torch_dtype": "float16",
                "quantization_config": {"quant_method": "awq", "bits": 4},
            }
        ),
        encoding="utf-8",
    )
    hfscan = required(
        "read a vLLM model's architecture, layers, quant and cache width from its "
        "HuggingFace config",
        lambda: importlib.import_module("mcgyvr.serving.hfscan"),
    )
    row = hfscan.scan(snapshot)
    assert row["arch"] == "Qwen2ForCausalLM"
    assert row["n_layer"] == 28
    assert "awq" in str(row["quant"]).lower()
    assert row["kv_bytes_per_token"] == 2 * 28 * 4 * 128 * 2
