"""Every documented way a unit asks for mtp puts it in the ``mtp`` class.

Owner decision: a llama.cpp unit asks to draft with the GGUF's own head in
any of three ways, and each is judged as ``mtp``, whether or not experts are
on the CPU beside it:

* ``--spec-type draft-mtp``, two words, in its ``argv`` or among its ``flags``;
* ``--spec-type=draft-mtp``, one word, which llama-server reads the same;
* ``speculative: mtp`` in its ``launch`` block (``units.launch`` in
  :mod:`mcgyvr.config`), which :mod:`mcgyvr.serving` renders as the two words
  only when it builds the unit — the fleet's judges read the block as written.

Any other ``--spec-type`` value, ``speculative: none``, and a vLLM unit are
judged as before.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr.fleet.tolerance import (
    CLASS_CPU_EXPERTS,
    CLASS_LLAMACPP,
    CLASS_MTP,
    CLASS_VLLM,
    tolerance_class,
)

BASE = ["--model", "/models/moe/y.gguf", "--parallel", "1", "-c", "8192", "-ngl", "99"]
OFFLOAD = ["--n-cpu-moe", "6"]


def _llamacpp(**launch: Any) -> dict[str, Any]:
    return {"engine": "llama.cpp", "launch": launch}


@pytest.mark.parametrize("offload", [[], OFFLOAD], ids=["alone", "beside_offload"])
def test_the_one_word_form_in_the_argv_is_mtp(offload: list[str]) -> None:
    unit = _llamacpp(argv=[*BASE, *offload, "--spec-type=draft-mtp"])
    assert tolerance_class(unit) == CLASS_MTP


def test_the_one_word_form_among_the_flags_is_mtp() -> None:
    unit = _llamacpp(flags=["--cpu-moe", "--spec-type=draft-mtp"])
    assert tolerance_class(unit) == CLASS_MTP


@pytest.mark.parametrize(
    "beside",
    [{}, {"n_cpu_moe": 6}, {"flags": ["--cpu-moe"]}, {"spec_draft_n_max": 3}],
    ids=["alone", "n_cpu_moe", "cpu_moe_flag", "draft_width"],
)
def test_speculative_mtp_in_the_launch_block_is_mtp(beside: dict[str, Any]) -> None:
    unit = _llamacpp(speculative="mtp", **beside)
    assert tolerance_class(unit) == CLASS_MTP


@pytest.mark.parametrize(
    ("launch", "expected"),
    [
        ({"argv": [*BASE, "--spec-type=ngram"]}, CLASS_LLAMACPP),
        ({"argv": [*BASE, *OFFLOAD, "--spec-type=draft-model"]}, CLASS_CPU_EXPERTS),
        ({"argv": [*BASE, "--spec-type="]}, CLASS_LLAMACPP),
        ({"speculative": "none"}, CLASS_LLAMACPP),
        ({"speculative": "none", "n_cpu_moe": 6}, CLASS_CPU_EXPERTS),
    ],
)
def test_any_other_request_is_judged_as_before(
    launch: dict[str, Any], expected: str
) -> None:
    assert tolerance_class(_llamacpp(**launch)) == expected


@pytest.mark.parametrize(
    "launch",
    [{"speculative": "mtp"}, {"argv": ["Qwen/y", "--spec-type=draft-mtp"]}],
)
def test_a_vllm_unit_is_vllm_however_it_asks(launch: dict[str, Any]) -> None:
    assert tolerance_class({"engine": "vllm", "launch": launch}) == CLASS_VLLM
