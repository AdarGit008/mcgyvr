"""A GGUF scan states every block's bytes and what lies outside the blocks.

Promise: ``ggufscan`` reports, read off the tensor table and nothing else, the
bytes of every block (all its tensors, not only its experts), the part of each
block held in two-dimensional tensors (what a tensor split divides; a
three-dimensional expert tensor is held whole), the input embedding, and the
rest outside every block with its own matrix part; the three parts sum to the
whole table. Each cached layer states the KV heads behind its widths, and a
model with no output head of its own says its embeddings are tied, because
llama.cpp then copies the input embedding onto the output layer's card. These
are what a split across cards is sized from.

The GGUF here is written by the test: an invented two-block model whose header
and tensor table are real GGUF and whose weights are absent, because the scan
never reads a weight.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from mcgyvr.serving import ggufscan

F32, F16, Q8_0 = 0, 1, 8


def _string(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack("<Q", len(raw)) + raw


def _kv(key: str, value: Any) -> bytes:
    if isinstance(value, str):
        return _string(key) + struct.pack("<I", 8) + _string(value)
    return _string(key) + struct.pack("<I", 4) + struct.pack("<I", value)


def _tensor(name: str, dims: tuple[int, ...], kind: int) -> bytes:
    head = _string(name) + struct.pack("<I", len(dims))
    head += b"".join(struct.pack("<Q", d) for d in dims)
    return head + struct.pack("<I", kind) + struct.pack("<Q", 0)


def write_gguf(path: Path, *, tied: bool = False, experts: bool = False) -> None:
    keys = {
        "general.architecture": "invented",
        "invented.block_count": 2,
        "invented.embedding_length": 64,
        "invented.attention.head_count": 8,
        "invented.attention.head_count_kv": 2,
        "invented.attention.key_length": 8,
        "invented.attention.value_length": 8,
    }
    tensors = [
        ("token_embd.weight", (64, 100), F16),
        ("output_norm.weight", (64,), F32),
    ]
    if not tied:
        tensors.append(("output.weight", (64, 100), Q8_0))
    for b in range(2):
        tensors += [
            (f"blk.{b}.attn_norm.weight", (64,), F32),
            (f"blk.{b}.attn_q.weight", (64, 64), F16),
            (f"blk.{b}.ffn_down.weight", (128, 64), Q8_0),
        ]
        if experts:
            tensors.append((f"blk.{b}.ffn_up_exps.weight", (64, 32, 4), F16))
    body = b"GGUF" + struct.pack("<I", 3)
    body += struct.pack("<Q", len(tensors)) + struct.pack("<Q", len(keys))
    body += b"".join(_kv(k, v) for k, v in keys.items())
    body += b"".join(_tensor(n, d, k) for n, d, k in tensors)
    path.write_bytes(body)


def scanned(tmp_path: Path, **kw: bool) -> dict[str, Any]:
    path = tmp_path / "example-model-small.gguf"
    write_gguf(path, **kw)
    # The scanner is held untyped on purpose: it ships to a rig as text.
    row: dict[str, Any] = ggufscan.scan(str(path))  # type: ignore[no-untyped-call]
    assert "error" not in row, row
    return row


def test_every_block_is_summed_whole_and_its_matrices_apart(tmp_path: Path) -> None:
    row = scanned(tmp_path)
    norm = 64 * 4
    q = 64 * 64 * 2
    down = 128 * 64 // 32 * 34
    assert row["bytes_by_block"] == {"0": norm + q + down, "1": norm + q + down}
    assert row["bytes_matrix_by_block"] == {"0": q + down, "1": q + down}


def test_the_input_and_the_rest_outside_the_blocks_are_kept_apart(
    tmp_path: Path,
) -> None:
    row = scanned(tmp_path)
    assert row["bytes_input"] == 64 * 100 * 2
    output_matrix = 64 * 100 // 32 * 34
    assert row["bytes_output_matrix"] == output_matrix
    assert row["bytes_output"] == output_matrix + 64 * 4


def test_the_parts_sum_to_the_whole_table(tmp_path: Path) -> None:
    row = scanned(tmp_path)
    parts = (
        row["bytes_input"] + row["bytes_output"] + sum(row["bytes_by_block"].values())
    )
    assert parts == row["bytes_total_tensors"]


def test_each_cached_layer_states_its_kv_heads(tmp_path: Path) -> None:
    row = scanned(tmp_path)
    assert [layer["heads"] for layer in row["kv_layers"]] == [2, 2]
    assert row["kv_layers"][0]["k_elems"] == 2 * 8
    assert row["n_head"] == 8


def test_an_expert_tensor_counts_in_its_block_and_not_as_a_divided_matrix(
    tmp_path: Path,
) -> None:
    row = scanned(tmp_path, experts=True)
    norm = 64 * 4
    q = 64 * 64 * 2
    down = 128 * 64 // 32 * 34
    up_exps = 64 * 32 * 4 * 2
    assert row["bytes_by_block"]["0"] == norm + q + down + up_exps
    assert row["bytes_matrix_by_block"]["0"] == q + down


def test_a_model_with_its_own_output_head_is_not_tied(tmp_path: Path) -> None:
    assert scanned(tmp_path)["tied_embeddings"] is False


def test_a_model_with_no_output_head_says_its_embeddings_are_tied(
    tmp_path: Path,
) -> None:
    row = scanned(tmp_path, tied=True)
    assert row["tied_embeddings"] is True
    assert row["bytes_output_matrix"] == 0
