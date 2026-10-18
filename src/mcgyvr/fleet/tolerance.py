"""A unit's tolerance class: the key its speed tolerances are stated by.

Two numbers, `warm_decode_class_pct` and `prefill_class_pct`, are stated per
tolerance class in the numbers file, so a unit is judged against the spread its
own way of running actually has. `tolerance_class` reads one resolved unit and
names its class: a vLLM unit is `vllm`, and a llama.cpp unit is `mtp` when it
drafts with the GGUF's own MTP head, `cpu_experts` when it keeps expert blocks
in host memory, and `llamacpp` otherwise. Nothing here reads a number or starts
a unit; it classifies the mapping it is handed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

CLASS_VLLM = "vllm"
CLASS_LLAMACPP = "llamacpp"
CLASS_CPU_EXPERTS = "cpu_experts"
#: A llama.cpp unit that drafts with the GGUF's own grafted MTP head: it launches
#: `--spec-type draft-mtp`, or declares `speculative: mtp`, which is the same
#: declaration stated in the fleet file instead of in the flags and the argv.
CLASS_MTP = "mtp"
#: Every class, in the order the per-class tolerance tables are asked for.
CLASSES: tuple[str, ...] = (CLASS_VLLM, CLASS_LLAMACPP, CLASS_CPU_EXPERTS, CLASS_MTP)

#: The llama.cpp flags that keep expert blocks in host memory: `--cpu-moe` keeps
#: them all off the card, and `--n-cpu-moe n` keeps the first n blocks' worth.
_CPU_MOE = "--cpu-moe"
_N_CPU_MOE = "--n-cpu-moe"
_CPU_EXPERT_FLAGS = frozenset({_CPU_MOE, _N_CPU_MOE})
#: The flag that names the draft type, and the draft type the MTP head runs as.
_SPEC_TYPE = "--spec-type"
_DRAFT_MTP = "draft-mtp"
#: The same flag and value as one token, which is how a launch may spell it.
_SPEC_TYPE_DRAFT_MTP = f"{_SPEC_TYPE}={_DRAFT_MTP}"
#: The `speculative` value a llama.cpp unit declares when it runs that head;
#: `none`, the default, drafts with nothing. Its argv spelling above is the same
#: declaration written as a flag, so a launch that says either one is of the MTP
#: class.
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
    """Whether an argv holds a flag that keeps expert blocks in host memory.

    That is a bare `--cpu-moe`, or an `--n-cpu-moe` whose next word is a count
    above zero; an `--n-cpu-moe` at the end of the argv, or one followed by
    something that is not a count, keeps nothing. Anything but a list is False.
    """
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
    """Whether a word list names the GGUF's own MTP head as the draft.

    Either spelling counts: the single word `--spec-type=draft-mtp`, or
    `--spec-type` and `draft-mtp` as two adjacent words. Anything but a list is
    False.
    """
    if not isinstance(words, list):
        return False
    return _SPEC_TYPE_DRAFT_MTP in words or any(
        words[index] == _SPEC_TYPE and words[index + 1] == _DRAFT_MTP
        for index in range(len(words) - 1)
        if isinstance(words[index], str) and isinstance(words[index + 1], str)
    )


def tolerance_class(unit: Mapping[str, Any]) -> str:
    """The tolerance class of one unit, as the per-class numbers are keyed.

    `engine: vllm` is `vllm` on its own. A llama.cpp unit is `mtp` when its
    launch declares `speculative: mtp` or spells `--spec-type draft-mtp` in its
    flags or argv, `cpu_experts` when it states a positive `n_cpu_moe` or keeps
    expert blocks in host memory by flag or argv, and `llamacpp` otherwise --
    the answer for a unit with no launch block at all.
    """
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
