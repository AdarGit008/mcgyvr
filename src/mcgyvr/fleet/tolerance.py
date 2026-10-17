""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

CLASS_VLLM = "vllm"
CLASS_LLAMACPP = "llamacpp"
CLASS_CPU_EXPERTS = "cpu_experts"
#
#
#
CLASS_MTP = "mtp"
#
CLASSES: tuple[str, ...] = (CLASS_VLLM, CLASS_LLAMACPP, CLASS_CPU_EXPERTS, CLASS_MTP)

#
_CPU_MOE = "--cpu-moe"
_N_CPU_MOE = "--n-cpu-moe"
_CPU_EXPERT_FLAGS = frozenset({_CPU_MOE, _N_CPU_MOE})
#
_SPEC_TYPE = "--spec-type"
_DRAFT_MTP = "draft-mtp"
#
_SPEC_TYPE_DRAFT_MTP = f"{_SPEC_TYPE}={_DRAFT_MTP}"
#
#
#
#
_SPECULATIVE_MTP = "mtp"


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
    ""
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
    ""
    if not isinstance(words, list):
        return False
    return _SPEC_TYPE_DRAFT_MTP in words or any(
        words[index] == _SPEC_TYPE and words[index + 1] == _DRAFT_MTP
        for index in range(len(words) - 1)
        if isinstance(words[index], str) and isinstance(words[index + 1], str)
    )


def tolerance_class(unit: Mapping[str, Any]) -> str:
    ""
    if unit.get("engine") == CLASS_VLLM:
        return CLASS_VLLM
    launch = unit.get("launch")
    if isinstance(launch, Mapping):
        if (
            launch.get("speculative") == _SPECULATIVE_MTP
            or _drafts_with_its_own_head(launch.get("argv"))
            or _drafts_with_its_own_head(launch.get("flags"))
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
