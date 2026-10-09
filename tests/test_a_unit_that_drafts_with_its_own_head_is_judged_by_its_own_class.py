"""A unit that drafts with its own head is judged by its own tolerance class.

Owner ruling, 2026-09-16, after the mtp-ornith window: ``srv2_ornith_mtp`` —
a llama.cpp unit whose launch argv carries ``--spec-type draft-mtp`` — gets a
class of its own, ``mtp``, and is not judged by ``cpu_experts``' numbers. Those
were measured on srv1 offload (48% warm decode, 1% prefill), not this regime:
the unit's own three cold starts spread 1.63% in warm decode and 4.29% in
prefill, so a live probe judged by the class's 1% prefill would have failed a
sample the lock itself accepted.

* :func:`mcgyvr.fleet.tolerance.tolerance_class` puts a llama.cpp unit whose
  argv (or ``flags``) carries ``--spec-type draft-mtp`` in ``mtp``, whether or
  not experts are on the CPU beside it; any other ``--spec-type`` value, and a
  vLLM unit whatever its argv says, are judged as before.
* Every other unit keeps the class it had: the ruling adds a class, it moves
  nobody. Checked on invented units, and on each unit the committed fleet
  declares against its class with the mtp request taken out, so the check
  holds whichever units the fleet carries.
* The lab's derived numbers state ``mtp`` in both judged fields: prefill at
  the 5% tolerance derived from the mtp-ornith window, warm decode at the same
  rule over the same three runs' decode samples, which is 2%. An absent
  ``mtp`` is refused by name, as any class is.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr.fleet.tolerance import (
    CLASS_CPU_EXPERTS,
    CLASS_LLAMACPP,
    CLASS_MTP,
    CLASS_VLLM,
    CLASSES,
    tolerance_class,
)

SPEC = ["--spec-type", "draft-mtp", "--spec-draft-n-max", "2"]
BASE = ["--model", "/models/moe/x.gguf", "--parallel", "1", "-c", "4096", "-ngl", "99"]

#: Units that do not ask for mtp, each with the class it had before the ruling.
#: Invented, so the check does not move when a unit joins or leaves the fleet.
BEFORE: dict[str, tuple[dict[str, Any], str]] = {
    "a_vllm_unit": ({"engine": "vllm", "launch": {"argv": ["Qwen/x"]}}, CLASS_VLLM),
    "a_plain_llamacpp_unit": (
        {"engine": "llama.cpp", "launch": {"argv": BASE}},
        CLASS_LLAMACPP,
    ),
    "an_unnamed_engine": ({"launch": {"argv": BASE}}, CLASS_LLAMACPP),
    "experts_on_the_cpu_in_the_argv": (
        {"engine": "llama.cpp", "launch": {"argv": [*BASE, "--n-cpu-moe", "8"]}},
        CLASS_CPU_EXPERTS,
    ),
    "experts_on_the_cpu_as_a_key": (
        {"engine": "llama.cpp", "launch": {"n_cpu_moe": 8}},
        CLASS_CPU_EXPERTS,
    ),
    "experts_on_the_cpu_among_the_flags": (
        {"engine": "llama.cpp", "launch": {"flags": ["--cpu-moe"]}},
        CLASS_CPU_EXPERTS,
    ),
}


def _llamacpp(argv: list[str], **launch: Any) -> dict[str, Any]:
    return {"engine": "llama.cpp", "launch": {"argv": argv, **launch}}


# --- the class -------------------------------------------------------------


def test_mtp_is_a_class_of_its_own() -> None:
    assert CLASS_MTP == "mtp"
    assert CLASS_MTP in CLASSES
    assert set(CLASSES) == {CLASS_VLLM, CLASS_LLAMACPP, CLASS_CPU_EXPERTS, CLASS_MTP}


@pytest.mark.parametrize("name", sorted(BEFORE))
def test_a_unit_that_does_not_ask_for_mtp_keeps_its_class(name: str) -> None:
    unit, before = BEFORE[name]
    assert tolerance_class(unit) == before


@pytest.mark.parametrize(
    "argv",
    [
        [*BASE, *SPEC],
        [*BASE[:2], "--n-cpu-moe", "8", *SPEC, *BASE[2:]],
        [*BASE, "--cpu-moe", *SPEC],
        [*SPEC, *BASE],
    ],
)
def test_draft_mtp_in_the_argv_is_mtp_with_or_without_experts_on_the_cpu(
    argv: list[str],
) -> None:
    assert tolerance_class(_llamacpp(argv)) == CLASS_MTP


def test_draft_mtp_among_the_flags_is_mtp() -> None:
    unit = {"engine": "llama.cpp", "launch": {"flags": SPEC}}
    assert tolerance_class(unit) == CLASS_MTP


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (
            [*BASE, "--spec-type", "draft-model", "--spec-draft-n-max", "2"],
            CLASS_LLAMACPP,
        ),
        ([*BASE, "--n-cpu-moe", "8", "--spec-type", "ngram"], CLASS_CPU_EXPERTS),
        ([*BASE, "--spec-type"], CLASS_LLAMACPP),
        ([*BASE, "draft-mtp"], CLASS_LLAMACPP),
        ([*BASE, "--spec-draft-n-max", "2"], CLASS_LLAMACPP),
    ],
)
def test_any_other_spec_type_or_a_bare_word_is_judged_as_before(
    argv: list[str], expected: str
) -> None:
    assert tolerance_class(_llamacpp(argv)) == expected


def test_a_vllm_unit_is_vllm_whatever_its_argv_says() -> None:
    unit = {"engine": "vllm", "launch": {"argv": ["Qwen/x", *SPEC]}}
    assert tolerance_class(unit) == CLASS_VLLM
