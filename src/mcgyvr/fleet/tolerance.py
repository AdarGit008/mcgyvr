"""One tolerance class per unit, so every judge of a unit reads one class.

Owner, 2026-09-15: a live unit is judged with measured class tolerances — vLLM,
llama.cpp, llama.cpp with experts on the CPU and, since 2026-09-16, llama.cpp
drafting with the GGUF's own MTP head — and each judged field has its own,
stated in ``tools/runs/derived.json``: warm decode those of
``records/measurements/fleet-identity-2026-09-11/tolerances.json``
(``engine.warm_decode_class_pct``), prefill those of
``records/measurements/fleet-identity-prefill-2026-09-12/README.md``
(``engine.prefill_class_pct``), and the ``mtp`` class's both from the
mtp-ornith window (``records/measurements/lock-fleets/mtp-ornith/``). The
probe's judge (:mod:`mcgyvr.fleet.probe`) and the lock's NVMe baseline check
(:mod:`mcgyvr.fleet.lock`) both ask :func:`tolerance_class`, so the two cannot
put one unit in two classes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

CLASS_VLLM = "vllm"
CLASS_LLAMACPP = "llamacpp"
CLASS_CPU_EXPERTS = "cpu_experts"
#: llama.cpp drafting with the GGUF's own grafted head (``--spec-type
#: draft-mtp``). Owner ruling, 2026-09-16, after the mtp-ornith window: its
#: numbers are its own — cpu_experts' were measured on srv1 offload and the
#: unit's three cold starts spread 1.63% in warm decode and 4.29% in prefill.
CLASS_MTP = "mtp"
#: Every class a unit can be in; ``tools/runs/derived.json`` states each.
CLASSES: tuple[str, ...] = (CLASS_VLLM, CLASS_LLAMACPP, CLASS_CPU_EXPERTS, CLASS_MTP)

#: The llama-server flags that put expert tensors on the CPU.
_CPU_MOE = "--cpu-moe"
_N_CPU_MOE = "--n-cpu-moe"
_CPU_EXPERT_FLAGS = frozenset({_CPU_MOE, _N_CPU_MOE})
#: The llama-server flag and value that run the GGUF's own MTP head as the draft.
_SPEC_TYPE = "--spec-type"
_DRAFT_MTP = "draft-mtp"


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _positive_digits(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.isascii()
        and value.isdigit()
        and int(value) > 0
    )


def _argv_keeps_experts_on_cpu(argv: Any) -> bool:
    """``--cpu-moe``, or ``--n-cpu-moe`` followed by a positive integer."""
    if not isinstance(argv, list):
        return False
    for index, token in enumerate(argv):
        if not isinstance(token, str):
            continue
        if token == _CPU_MOE:
            return True
        if (
            token == _N_CPU_MOE
            and index + 1 < len(argv)
            and _positive_digits(argv[index + 1])
        ):
            return True
    return False


def _drafts_with_its_own_head(words: Any) -> bool:
    """``--spec-type`` followed by ``draft-mtp``, in an argv or a flags list."""
    if not isinstance(words, list):
        return False
    return any(
        words[index] == _SPEC_TYPE and words[index + 1] == _DRAFT_MTP
        for index in range(len(words) - 1)
        if isinstance(words[index], str) and isinstance(words[index + 1], str)
    )


def tolerance_class(unit: Mapping[str, Any]) -> str:
    """The tolerance class of one ``fleet.yaml`` unit block.

    ``engine: vllm`` is ``vllm``. Any other unit is llama.cpp (an absent engine
    means llama.cpp, ``units.engine`` in :mod:`mcgyvr.config`), and it is
    ``mtp`` when its launch drafts with the GGUF's own head — ``--spec-type``
    followed by ``draft-mtp`` in its ``argv`` or among its ``flags`` (owner
    ruling, 2026-09-16), whether or not experts are on the CPU beside it —
    ``cpu_experts`` when its launch keeps experts on the CPU, ``llamacpp``
    otherwise. The launch keeps them there with a positive ``n_cpu_moe``, with
    ``--cpu-moe`` / ``--n-cpu-moe`` among its ``flags``, or with ``--cpu-moe``
    or ``--n-cpu-moe`` followed by a positive integer in its ``argv`` (a locked
    unit's launch, verbatim). A value after ``--n-cpu-moe`` in the argv that is
    missing or not an integer does not count, and neither does ``0``. Any
    other ``--spec-type`` value is not a class: the head is the one the
    window measured.
    """
    if unit.get("engine") == CLASS_VLLM:
        return CLASS_VLLM
    launch = unit.get("launch")
    if isinstance(launch, Mapping):
        if _drafts_with_its_own_head(launch.get("argv")) or _drafts_with_its_own_head(
            launch.get("flags")
        ):
            return CLASS_MTP
        if _positive_int(launch.get("n_cpu_moe")):
            return CLASS_CPU_EXPERTS
        flags = launch.get("flags")
        if isinstance(flags, list) and any(
            isinstance(flag, str) and flag in _CPU_EXPERT_FLAGS for flag in flags
        ):
            return CLASS_CPU_EXPERTS
        if _argv_keeps_experts_on_cpu(launch.get("argv")):
            return CLASS_CPU_EXPERTS
    return CLASS_LLAMACPP
