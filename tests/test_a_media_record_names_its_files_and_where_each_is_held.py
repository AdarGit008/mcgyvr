"""A media record names its files, each pinned, and where its unit holds each.

Owner, Round 10 (orchestrator calls, accepted): the model knowledge gains
optional ``files`` (each pinned by its sha256, or by its git oid where the Hub
keeps no sha256) and a stated ``working_set``; context and KV cache apply to
text models only.

Promises:

* the shipped catalog holds an image model, a voice and a speech recogniser,
  one each, as media records; each file a media record names is pinned to a
  40-digit revision, and every file of the image model, which is fetched one
  file at a time, carries a sha256;
* a media record carries no context or KV cache figure, and a record that
  does is refused by name; so is one whose files are held to no hash or to
  two, whose working set leaves a file out, or that mixes a media engine with
  a text engine;
* a text record cannot carry ``files`` or a ``working_set``;
* a media record written to the cache reads back as it was.

The records refused here are invented; the shipped catalog is read.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from mcgyvr.knowledge import record as kr
from mcgyvr.knowledge import store as ks

REV = "1" * 40
DAY = "2026-10-08"


def _bytes(value: int, file: str) -> dict[str, Any]:
    return {
        "value": value,
        "kind": "fact",
        "source": f"hub-api:invented-org/Invented-Image@{REV}/{file}",
        "read_at": DAY,
    }


_IMAGE: dict[str, Any] = {
    "model_id": "invented-org/Invented-Image",
    "quant": "Q4_K_S",
    "engines": ["comfyui"],
    "files": [
        {
            "repo": "invented-org/Invented-Image",
            "revision": REV,
            "file": "denoiser.gguf",
            "sha256": "a" * 64,
            "bytes": _bytes(6_000_000_000, "denoiser.gguf"),
        },
        {
            "repo": "invented-org/Invented-Image",
            "revision": REV,
            "file": "config.json",
            "git_oid": "b" * 40,
            "bytes": _bytes(2_000, "config.json"),
        },
    ],
    "working_set": {"card": ["denoiser.gguf"], "ram": ["config.json"]},
    "scores": [],
    "serves": ["media-gen"],
}


def _refused(raw: dict[str, Any], *words: str) -> None:
    with pytest.raises(kr.KnowledgeError) as caught:
        kr.parse_record(raw, "invented", shipped=True)
    for word in words:
        assert word in str(caught.value), str(caught.value)


def test_the_shipped_catalog_holds_one_image_model_one_voice_and_one_recogniser() -> (
    None
):
    media = [one for one in ks.shipped() if one.is_media]
    assert sorted(one.part or "" for one in media) == ["asr", "image", "tts"]
    for one in media:
        assert one.context_length is None and one.kv_bytes_per_token is None
        assert "media-gen" in one.serves
        for file in one.files:
            assert len(file.revision) == 40, (one.model_id, file.file)
            assert (file.sha256 is None) != (file.git_oid is None)
    (image,) = [one for one in media if one.part == "image"]
    assert image.files and all(f.sha256 for f in image.files)
    assert image.working_set is not None and image.working_set.card


def test_an_invented_media_record_reads_and_sums_its_files() -> None:
    one = kr.parse_record(copy.deepcopy(_IMAGE), "invented", shipped=True)
    assert one.is_media and one.part == "image"
    assert one.total_bytes == 6_000_002_000
    assert one.size_bytes is None
    names = [name for name, _number in one.numbers()]
    assert "files[denoiser.gguf].bytes" in names


@pytest.mark.parametrize("field", ["context_length", "kv_bytes_per_token"])
def test_a_media_record_with_a_text_models_figure_is_refused(field: str) -> None:
    raw = copy.deepcopy(_IMAGE)
    raw[field] = _bytes(4096, "config.json")
    _refused(raw, field, "text model")


def test_a_file_held_to_no_hash_or_to_two_is_refused() -> None:
    raw = copy.deepcopy(_IMAGE)
    del raw["files"][0]["sha256"]
    _refused(raw, "sha256", "git_oid")
    raw = copy.deepcopy(_IMAGE)
    raw["files"][1]["sha256"] = "c" * 64
    _refused(raw, "exactly one")


def test_a_working_set_that_leaves_a_file_out_is_refused() -> None:
    raw = copy.deepcopy(_IMAGE)
    raw["working_set"] = {"card": ["denoiser.gguf"], "ram": []}
    _refused(raw, "working_set", "config.json")


def test_files_without_a_working_set_are_refused() -> None:
    raw = copy.deepcopy(_IMAGE)
    del raw["working_set"]
    _refused(raw, "working_set")


def test_a_media_engine_beside_a_text_engine_is_refused() -> None:
    raw = copy.deepcopy(_IMAGE)
    raw["engines"] = ["comfyui", "llama.cpp"]
    _refused(raw, "mix")


def test_a_text_record_cannot_carry_files() -> None:
    (text,) = [one for one in ks.shipped() if not one.is_media][:1]
    raw = kr.dump_record(text)
    raw["files"] = copy.deepcopy(_IMAGE["files"])
    _refused(raw, "text model", "files")


def test_a_media_record_reads_back_as_it_was_written() -> None:
    for one in [r for r in ks.shipped() if r.is_media]:
        again = kr.parse_record(kr.dump_record(one), "again", shipped=True)
        assert again == one
