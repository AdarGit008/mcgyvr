"""The safetensors scanner reports bytes from the tensor table, by position.

Bits-per-weight is a guess; the tensor table is not. The row a checkpoint
directory yields states the bytes of every tensor, split into each decoder
block, the input embedding and the rest, with a second count of the tensors a
tensor-parallel split divides (two dimensions or more), and the parts always
add up to the whole. A checkpoint in several shards is read in every shard.
Weights are never read: the checkpoints here hold zero bytes of data.
"""

from __future__ import annotations

from pathlib import Path

from mcgyvr.serving import safetensorscan
from tests import safetensors_checkpoint as ckpt


def _invariant(row: dict[str, object]) -> None:
    by_block = row["bytes_by_block"]
    assert isinstance(by_block, dict)
    assert (
        row["bytes_input"] + row["bytes_output"] + sum(by_block.values())  # type: ignore[operator]
        == row["bytes_total_tensors"]
    )


def test_block_input_output_and_matrix_bytes_are_summed_from_the_table(
    tmp_path: Path,
) -> None:
    n = 3
    spec = ckpt.decoder_spec(n)
    d = ckpt.make(tmp_path / "box-a-model", spec, ckpt.base_config(num_hidden_layers=n))

    row = safetensorscan.scan(str(d))

    assert "error" not in row
    q = ckpt.nbytes("BF16", [8, 8])
    up = ckpt.nbytes("BF16", [16, 8])
    norm = ckpt.nbytes("BF16", [8])
    embed = ckpt.nbytes("BF16", [32, 8])
    assert row["bytes_by_block"] == {str(i): q + up + norm for i in range(n)}
    assert row["bytes_matrix_by_block"] == {str(i): q + up for i in range(n)}
    assert row["bytes_input"] == embed
    assert row["bytes_output"] == norm + embed
    assert row["bytes_output_matrix"] == embed
    assert row["bytes_total_tensors"] == sum(
        ckpt.nbytes(dt, shape) for dt, shape in spec.values()
    )
    _invariant(row)
    assert row["file"] == str(d)
    assert row["size_bytes"] == (d / "model.safetensors").stat().st_size


def test_shards_are_summed_and_agree_with_the_same_tensors_in_one_file(
    tmp_path: Path,
) -> None:
    spec = ckpt.decoder_spec(4)
    config = ckpt.base_config(num_hidden_layers=4)
    whole = ckpt.make(tmp_path / "whole", spec, config)

    sharded = tmp_path / "sharded"
    sharded.mkdir()
    names = list(spec)
    half = len(names) // 2
    first = {k: spec[k] for k in names[:half]}
    second = {k: spec[k] for k in names[half:]}
    ckpt.write_shard(sharded / "model-00001-of-00002.safetensors", first)
    ckpt.write_shard(sharded / "model-00002-of-00002.safetensors", second)
    ckpt.write_config(sharded, config)

    one = safetensorscan.scan(str(whole))
    two = safetensorscan.scan(str(sharded))

    for key in (
        "bytes_total_tensors",
        "bytes_by_block",
        "bytes_matrix_by_block",
        "bytes_input",
        "bytes_output",
        "bytes_output_matrix",
    ):
        assert two[key] == one[key], key
    _invariant(two)
    assert two["size_bytes"] == sum(
        p.stat().st_size for p in sharded.glob("*.safetensors")
    )
    assert len(list(sharded.glob("*.safetensors"))) == 2


def test_packed_quantised_tensors_are_two_dimensional_and_split_with_the_matrices(
    tmp_path: Path,
) -> None:
    """AWQ/GPTQ ``qweight``/``qzeros``/``scales`` are 2-D, so they split; a bias
    or a norm is 1-D and is replicated. The block also sits under a nested
    ``language_model`` prefix, which is still ``layers.<i>``."""
    p = "model.language_model.layers.0"
    spec: ckpt.Spec = {
        "model.language_model.embed_tokens.weight": ("F16", [32, 8]),
        f"{p}.self_attn.q_proj.qweight": ("I32", [8, 2]),
        f"{p}.self_attn.q_proj.qzeros": ("I32", [1, 2]),
        f"{p}.self_attn.q_proj.scales": ("F16", [1, 8]),
        f"{p}.self_attn.q_proj.bias": ("F16", [8]),
        "lm_head.weight": ("F16", [32, 8]),
    }
    quant = {"quant_method": "awq", "bits": 4, "group_size": 8}
    config = ckpt.base_config(num_hidden_layers=1, quantization_config=quant)
    d = ckpt.make(tmp_path / "quantised", spec, config)

    row = safetensorscan.scan(str(d))

    matrix = (
        ckpt.nbytes("I32", [8, 2])
        + ckpt.nbytes("I32", [1, 2])
        + ckpt.nbytes("F16", [1, 8])
    )
    assert row["bytes_matrix_by_block"] == {"0": matrix}
    assert row["bytes_by_block"] == {"0": matrix + ckpt.nbytes("F16", [8])}
    assert row["bytes_input"] == ckpt.nbytes("F16", [32, 8])
    assert row["bytes_output"] == row["bytes_output_matrix"]
    assert row["quantization_config"] == quant
    _invariant(row)


def test_a_config_without_quantisation_records_null_and_states_its_dtype(
    tmp_path: Path,
) -> None:
    d = ckpt.make(tmp_path / "plain", ckpt.decoder_spec(2), ckpt.base_config())

    row = safetensorscan.scan(str(d))

    assert row["quantization_config"] is None
    assert row["dtype"] == "bfloat16"
    assert row["recurrent_blocks"] == []
    assert row["n_recurrent"] == 0


def test_a_nested_text_config_supplies_the_geometry_and_the_architecture(
    tmp_path: Path,
) -> None:
    config = {
        "model_type": "example-multimodal",
        "text_config": ckpt.base_config(model_type="example-text"),
    }
    d = ckpt.make(tmp_path / "nested", ckpt.decoder_spec(2), config)

    row = safetensorscan.scan(str(d))

    assert row["arch"] == "example-text"
    assert (row["n_layer"], row["n_embd"], row["n_head"]) == (2, 8, 4)
    assert row["n_head_kv"] == 2
