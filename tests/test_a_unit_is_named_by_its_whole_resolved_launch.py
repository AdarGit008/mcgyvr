"""A unit is named by its whole resolved launch, and a tag is not an image.

RED. ``mcgyvr.fleet.unit`` does not exist. The intent is
``records/plans/fleet-identity.md`` §1 (owner, 2026-09-11).

``unt-`` hashes everything that decides what the process is: the engine, the
resolved image id, the weights' sha256, the argv, the environment and the
card's compute capability. There is no hand-kept field list. The vLLM v0.26.0
research behind §8 found a unit's KV capacity moved by flags whose effect
differs per model family: ``--kv-cache-dtype`` (fp8 moves an sm_86 card off
FlashAttention), ``--kv-cache-memory-bytes``, ``--max-model-len``,
``--max-num-seqs``, ``--max-num-batched-tokens``, eager or compile mode. A list
misses the next one silently; a hash of the launch cannot.

A tag is not an identity. ``mcgyvr emit`` writes an image "as a tag or a
digest" (``src/mcgyvr/config.py``, the unit's ``image`` field), and srv1's is
the local tag ``llamacpp:b10644-L3``, which a rebuild replaces under the same
string. What is hashed is the image's ``sha256:`` Id.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from tests.red_port.conftest import required

LAUNCH: dict[str, Any] = {
    "engine": "vllm",
    "image_id": "sha256:" + "f" * 64,
    "weights_sha256": "a" * 64,
    "argv": [
        "--model",
        "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ",
        "--port",
        "8002",
        "--gpu-memory-utilization",
        "0.60",
        "--kv-cache-memory-bytes",
        "2147483648",
        "--max-model-len",
        "4096",
        "--max-num-seqs",
        "8",
    ],
    "env": {"CUDA_VISIBLE_DEVICES": "0", "VLLM_LOGGING_LEVEL": "INFO"},
    "gpu_cc": "8.6",
}


def _unit_id() -> Any:
    return required(
        "name a unit by its whole resolved launch: engine, image id, weights, "
        "argv, environment and card generation",
        lambda: importlib.import_module("mcgyvr.fleet.unit").unit_id,
    )


def _with(argv: list[str], flag: str, value: str) -> list[str]:
    at = argv.index(flag)
    return [*argv[: at + 1], value, *argv[at + 2 :]]


def test_a_unit_id_is_unt_plus_a_digest_of_its_launch() -> None:
    unit_id = _unit_id()
    named = unit_id(LAUNCH)
    assert named.startswith("unt-"), named
    reordered = {**LAUNCH, "env": dict(reversed(list(LAUNCH["env"].items())))}
    assert unit_id(reordered) == named, "the environment is a mapping, not a list"


def test_any_flag_image_weights_environment_or_card_is_a_new_unit() -> None:
    unit_id = _unit_id()
    base = unit_id(LAUNCH)
    argv: list[str] = LAUNCH["argv"]
    variants: dict[str, dict[str, Any]] = {
        "an fp8 KV cache": {**LAUNCH, "argv": [*argv, "--kv-cache-dtype", "fp8"]},
        "another batch width": {
            **LAUNCH,
            "argv": _with(argv, "--max-num-seqs", "6"),
        },
        "another pinned KV size": {
            **LAUNCH,
            "argv": _with(argv, "--kv-cache-memory-bytes", "1073741824"),
        },
        "a rebuilt image": {**LAUNCH, "image_id": "sha256:" + "e" * 64},
        "other weights": {**LAUNCH, "weights_sha256": "b" * 64},
        "another environment": {
            **LAUNCH,
            "env": {**LAUNCH["env"], "VLLM_LOGGING_LEVEL": "DEBUG"},
        },
        "another card generation": {**LAUNCH, "gpu_cc": "7.5"},
        "another engine": {**LAUNCH, "engine": "llama.cpp"},
    }
    for why, launch in variants.items():
        assert unit_id(launch) != base, f"{why} must name a different unit"


def test_a_tag_is_not_an_image_id() -> None:
    unit_id = _unit_id()
    with pytest.raises(ValueError, match="image"):
        unit_id({**LAUNCH, "image_id": "llamacpp:b10644-L3"})


def test_a_launch_missing_a_field_is_refused_not_hashed() -> None:
    """A partial launch hashed would be a name for a process nobody resolved."""
    unit_id = _unit_id()
    for field in LAUNCH:
        partial = {key: value for key, value in LAUNCH.items() if key != field}
        with pytest.raises(ValueError, match=field):
            unit_id(partial)
