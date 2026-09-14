"""One tolerance class per unit, so every judge of a unit reads one number.

Owner, 2026-09-15: a live unit's warm decode and prefill are judged with the
measured class tolerances of
``records/measurements/fleet-identity-2026-09-11/tolerances.json`` — vLLM,
llama.cpp, and llama.cpp with experts on the CPU — stated in
``tools/runs/derived.json`` (``engine.warm_decode_class_pct``). The probe's
judge (:mod:`mcgyvr.fleet.probe`) and the lock's NVMe baseline check
(:mod:`mcgyvr.fleet.lock`) both ask :func:`tolerance_class`, so the two cannot
weigh one unit against two numbers.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

CLASS_VLLM = "vllm"
CLASS_LLAMACPP = "llamacpp"
CLASS_CPU_EXPERTS = "cpu_experts"
#: Every class a unit can be in; ``tools/runs/derived.json`` states each.
CLASSES: tuple[str, ...] = (CLASS_VLLM, CLASS_LLAMACPP, CLASS_CPU_EXPERTS)

#: The llama-server flags that put expert tensors on the CPU.
_CPU_EXPERT_FLAGS = frozenset({"--cpu-moe", "--n-cpu-moe"})


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def tolerance_class(unit: Mapping[str, Any]) -> str:
    """The tolerance class of one ``fleet.yaml`` unit block.

    ``engine: vllm`` is ``vllm``. Any other unit is llama.cpp (an absent engine
    means llama.cpp, ``units.engine`` in :mod:`mcgyvr.config`), and it is
    ``cpu_experts`` when its launch keeps experts on the CPU — a positive
    ``n_cpu_moe``, or ``--cpu-moe`` / ``--n-cpu-moe`` among its flags — and
    ``llamacpp`` otherwise.
    """
    if unit.get("engine") == CLASS_VLLM:
        return CLASS_VLLM
    launch = unit.get("launch")
    if isinstance(launch, Mapping):
        if _positive_int(launch.get("n_cpu_moe")):
            return CLASS_CPU_EXPERTS
        flags = launch.get("flags")
        if isinstance(flags, list) and any(
            isinstance(flag, str) and flag in _CPU_EXPERT_FLAGS for flag in flags
        ):
            return CLASS_CPU_EXPERTS
    return CLASS_LLAMACPP
