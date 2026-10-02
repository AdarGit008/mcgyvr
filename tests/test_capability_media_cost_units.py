"""A media model row declares its cost in the unit its modality is priced in.

The capability table keeps one contract for every modality: estimates by card
class, one card read per class, and a row is a cost to serve, never a quality
figure. A media row keeps the contract with a modality-appropriate unit:

* image: ``seconds_per_image`` at a stated ``resolution``;
* video: ``seconds_per_clip`` at a stated frame budget;
* tts: a scalar ``rtf`` at a stated ``sample_rate_hz``, with a ``cpu_only``
  marker for a rung that needs no card.

These rows are invented and written to a temporary table; none is a shipped
estimate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcgyvr import cli
from mcgyvr.capability import GB_PER_GIB, CapabilityTableError, load
from tests.table_fixture import CLASSES, reading, table_document, write_table

FIRST = str(CLASSES[0]["id"])


def _image_row() -> dict[str, Any]:
    return {
        "id": "media-image",
        "family": "sdxl",
        "params_b": 3.5,
        "weights_gb": 6.9,
        "vram_gb_working": 8.0,
        "quant": "fp16",
        "resolution": "1024x1024",
        "steps": 4,
        "vae_decode_gb": 1.2,
        "seconds_per_image": [reading(FIRST, value=1.8)],
    }


def _refusal(tmp_path: Path, document: dict[str, Any]) -> str:
    path = write_table(tmp_path, document)
    with pytest.raises(CapabilityTableError) as refused:
        load(path)
    said = str(refused.value)
    assert str(path) in said, said
    return said


def test_an_image_row_loads_with_seconds_per_image_and_its_media_fields(
    tmp_path: Path,
) -> None:
    table = load(write_table(tmp_path, table_document(rows=[_image_row()])))

    model = table.models[0]
    assert model.seconds_per_image
    assert model.seconds_per_image[0].value == 1.8
    assert model.seconds_per_image[0].card_class == FIRST
    assert model.resolution == "1024x1024"
    assert model.steps == 4.0
    assert model.vae_decode_gb == 1.2


def test_model_spec_converts_the_decimal_vae_spike_to_gib(tmp_path: Path) -> None:
    table = load(write_table(tmp_path, table_document(rows=[_image_row()])))

    model = table.models[0]
    assert cli._model_spec(model, moe=False).vae_decode_gb == pytest.approx(
        1.2 / GB_PER_GIB
    )


def test_a_video_row_loads_with_seconds_per_clip_and_its_media_fields(
    tmp_path: Path,
) -> None:
    model = {
        "id": "media-video",
        "family": "ltx-video",
        "params_b": 2.0,
        "weights_gb": 4.1,
        "vram_gb_working": 5.0,
        "quant": "bf16",
        "resolution": "768x512",
        "frames": 121,
        "temporal_compress": 8,
        "seconds_per_clip": [reading(FIRST, value=9.5)],
    }
    table = load(write_table(tmp_path, table_document(rows=[model])))

    loaded = table.models[0]
    assert loaded.seconds_per_clip
    assert loaded.seconds_per_clip[0].value == 9.5
    assert loaded.resolution == "768x512"
    assert loaded.frames == 121.0
    assert loaded.temporal_compress == 8.0


def test_a_tts_row_loads_with_rtf_sample_rate_and_cpu_only(tmp_path: Path) -> None:
    model = {
        "id": "media-tts",
        "family": "piper",
        "params_b": 0.08,
        "weights_gb": 0.1,
        "vram_gb_working": 0.0,
        "quant": "onnx",
        "sample_rate_hz": 22050,
        "rtf": 0.25,
        "cpu_only": True,
    }
    table = load(write_table(tmp_path, table_document(rows=[model])))

    loaded = table.models[0]
    assert loaded.rtf == 0.25
    assert loaded.sample_rate_hz == 22050.0
    assert loaded.cpu_only is True


def test_a_media_cost_list_of_another_shape_is_refused_by_name(tmp_path: Path) -> None:
    model = _image_row()
    model["seconds_per_image"] = [0.5]

    said = _refusal(tmp_path, table_document(rows=[model]))

    assert "seconds_per_image" in said, said
    assert "media-image" in said, said


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("rtf", "fast"),
        ("cpu_only", "yes"),
        ("steps", "four"),
        ("vae_decode_gb", "large"),
        ("frames", "many"),
        ("temporal_compress", "often"),
        ("sample_rate_hz", "high"),
        ("resolution", ""),
    ],
)
def test_a_media_row_scalar_of_another_shape_is_refused_by_name(
    tmp_path: Path, key: str, value: Any
) -> None:
    model = _image_row()
    model[key] = value

    said = _refusal(tmp_path, table_document(rows=[model]))

    assert repr(key) in said, said
    assert "media-image" in said, said
