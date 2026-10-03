"""The safetensors scanner states each caching layer and refuses what it cannot size.

The cache geometry comes from ``config.json``: heads from
``num_key_value_heads`` (``num_attention_heads`` when absent, the config's own
convention), width from ``head_dim`` or ``hidden_size // num_attention_heads``.
Which layers slide comes from ``layer_types`` and from nothing else: a window
declared with no per-layer list is stated as unknown, the way ggufscan states
it, because an assumed split is wrong on checkpoints that are not alternating.
What the scanner does not size is refused by name rather than guessed: a dtype
it has no width for, a header that disagrees with the bytes its dtype implies,
a truncated file, a layer kind other than full or sliding attention.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.serving import safetensorscan
from tests import safetensors_checkpoint as ckpt


def _scan(
    tmp_path: Path, config: dict[str, object], n_layer: int = 2
) -> dict[str, object]:
    d = ckpt.make(tmp_path / "model", ckpt.decoder_spec(n_layer), config)
    return safetensorscan.scan(str(d))


def test_heads_and_head_dim_come_from_the_config(tmp_path: Path) -> None:
    row = _scan(tmp_path, ckpt.base_config(num_key_value_heads=2, head_dim=6))

    assert row["n_head_kv"] == 2
    layers = row["kv_layers"]
    assert isinstance(layers, list) and len(layers) == 2
    assert layers[1] == {
        "layer": 1,
        "is_swa": False,
        "k_elems": 12,
        "v_elems": 12,
        "heads": 2,
    }


def test_head_dim_defaults_to_hidden_size_over_heads(tmp_path: Path) -> None:
    row = _scan(tmp_path, ckpt.base_config(num_key_value_heads=2))

    layers = row["kv_layers"]
    assert isinstance(layers, list)
    assert {(r["k_elems"], r["v_elems"]) for r in layers} == {(2 * (8 // 4),) * 2}


def test_absent_kv_heads_mean_the_attention_head_count(tmp_path: Path) -> None:
    config = ckpt.base_config()
    del config["num_key_value_heads"]

    row = _scan(tmp_path, config)

    assert row["n_head_kv"] == row["n_head"] == 4
    layers = row["kv_layers"]
    assert isinstance(layers, list) and layers[0]["heads"] == 4


def test_layer_types_say_which_layers_slide(tmp_path: Path) -> None:
    types = ["sliding_attention", "full_attention", "sliding_attention"]
    row = _scan(
        tmp_path,
        ckpt.base_config(num_hidden_layers=3, sliding_window=4, layer_types=types),
        n_layer=3,
    )

    layers = row["kv_layers"]
    assert isinstance(layers, list)
    assert [r["is_swa"] for r in layers] == [True, False, True]
    assert row["sliding_window"] == 4


def test_a_window_without_a_per_layer_split_leaves_every_layer_unknown(
    tmp_path: Path,
) -> None:
    row = _scan(tmp_path, ckpt.base_config(sliding_window=4))

    layers = row["kv_layers"]
    assert isinstance(layers, list)
    assert [r["is_swa"] for r in layers] == [None, None]


def test_a_window_switched_off_and_no_window_slide_nothing(tmp_path: Path) -> None:
    off = _scan(
        tmp_path / "off",
        ckpt.base_config(sliding_window=4, use_sliding_window=False),
    )
    none = _scan(tmp_path / "none", ckpt.base_config())

    for row in (off, none):
        layers = row["kv_layers"]
        assert isinstance(layers, list)
        assert [r["is_swa"] for r in layers] == [False, False]


def test_a_layer_type_other_than_full_or_sliding_is_refused_by_name(
    tmp_path: Path,
) -> None:
    row = _scan(
        tmp_path,
        ckpt.base_config(layer_types=["full_attention", "example_recurrent"]),
    )

    assert "example_recurrent" in str(row["error"])
    assert row["file"] == str(tmp_path / "model")
    assert "kv_layers" not in row


def test_an_unknown_dtype_is_refused_by_name(tmp_path: Path) -> None:
    spec = ckpt.decoder_spec(2)
    spec["model.layers.0.example.weight"] = ("EXAMPLE_DT", [8, 8])
    d = tmp_path / "model"
    d.mkdir()
    ckpt.write_shard(d / "model.safetensors", spec, widths={"EXAMPLE_DT": 1})
    ckpt.write_config(d, ckpt.base_config())

    row = safetensorscan.scan(str(d))

    assert "EXAMPLE_DT" in str(row["error"])
    assert "bytes_total_tensors" not in row


def test_a_dtype_that_disagrees_with_the_offsets_is_refused(tmp_path: Path) -> None:
    """Laid out as 2 bytes per element but stated as F32 (4): the file's own
    offsets say the table of widths is wrong for it, and no sum is trusted."""
    spec = ckpt.decoder_spec(2)
    d = tmp_path / "model"
    d.mkdir()
    ckpt.write_shard(
        d / "model.safetensors",
        spec,
        claim={"model.norm.weight": ("F32", [8])},
    )
    ckpt.write_config(d, ckpt.base_config())

    row = safetensorscan.scan(str(d))

    assert "model.norm.weight" in str(row["error"])
    assert "bytes_total_tensors" not in row


def test_a_truncated_shard_is_refused(tmp_path: Path) -> None:
    d = ckpt.make(tmp_path / "model", ckpt.decoder_spec(2), ckpt.base_config())
    shard = d / "model.safetensors"
    shard.write_bytes(shard.read_bytes()[:-1])

    row = safetensorscan.scan(str(d))

    assert "truncated" in str(row["error"])


def test_a_directory_without_a_config_or_weights_is_refused_by_name(
    tmp_path: Path,
) -> None:
    no_config = tmp_path / "no-config"
    no_config.mkdir()
    ckpt.write_shard(no_config / "model.safetensors", ckpt.decoder_spec(1))
    no_weights = tmp_path / "no-weights"
    no_weights.mkdir()
    ckpt.write_config(no_weights, ckpt.base_config())

    assert "config.json" in str(safetensorscan.scan(str(no_config))["error"])
    assert "safetensors" in str(safetensorscan.scan(str(no_weights))["error"])


@pytest.mark.parametrize(
    "missing", ["num_hidden_layers", "hidden_size", "num_attention_heads"]
)
def test_a_geometry_field_the_config_does_not_state_is_refused_by_name(
    tmp_path: Path, missing: str
) -> None:
    config = ckpt.base_config()
    del config[missing]

    row = _scan(tmp_path, config)

    assert missing in str(row["error"])
