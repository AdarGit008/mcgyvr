"""A launch argv carrying the spec flags passes admission unchanged.

Two fleet gates read a locked unit's ``launch.argv``: the tolerance class
(:func:`mcgyvr.fleet.tolerance.tolerance_class`, which looks for ``--cpu-moe``
/ ``--n-cpu-moe``) and the locked renderer (``emit._locked_service``, which
copies the argv into the compose ``command`` verbatim). ``--spec-type
draft-mtp`` and ``--spec-draft-n-max 2`` must pass both untouched: the class
is still decided by the expert flags alone, and the rendered command is the
argv, in order, with nothing dropped, added or reordered.
"""

from __future__ import annotations

from typing import Any

from mcgyvr import emit
from mcgyvr.fleet.tolerance import (
    CLASS_CPU_EXPERTS,
    CLASS_LLAMACPP,
    tolerance_class,
)

SPEC = ["--spec-type", "draft-mtp", "--spec-draft-n-max", "2"]
BASE = [
    "--model",
    "/models/moe/Ornith-1.0-35B_Q2_K-AllGPU.gguf",
    "--parallel",
    "1",
    "--port",
    "8080",
    "-b",
    "512",
    "-ub",
    "512",
    "-c",
    "4096",
    "-fa",
    "on",
    "-ngl",
    "99",
    "-t",
    "10",
]


def locked(argv: list[str]) -> dict[str, Any]:
    return {
        "rig": "srv2",
        "address": "http://srv2:8080",
        "engine": "llama.cpp",
        "image": "ghcr.io/ggml-org/llama.cpp:server-cuda-b10644",
        "model": "Ornith-1.0-35B_Q2_K-AllGPU",
        "container": "mcgyvr-srv2-ornith",
        "unit_id": "unt-" + "0" * 64,
        "launch": {
            "argv": argv,
            "env": {"LLAMA_ARG_HOST": "0.0.0.0"},
            "volumes": ["/home/someone/models:/models:ro"],
        },
    }


def test_spec_flags_beside_n_cpu_moe_are_still_cpu_experts() -> None:
    argv = [*BASE[:2], "--n-cpu-moe", "8", *SPEC, *BASE[2:]]
    assert tolerance_class(locked(argv)) == CLASS_CPU_EXPERTS


def test_spec_flags_alone_are_still_llamacpp() -> None:
    assert tolerance_class(locked([*BASE, *SPEC])) == CLASS_LLAMACPP


def test_the_draft_width_is_never_read_as_an_expert_count() -> None:
    """``--spec-draft-n-max 2`` right after ``--n-cpu-moe 0`` does not promote."""
    argv = [*BASE[:2], "--n-cpu-moe", "0", *SPEC, *BASE[2:]]
    assert tolerance_class(locked(argv)) == CLASS_LLAMACPP


def test_the_locked_renderer_copies_the_argv_verbatim() -> None:
    argv = [*BASE[:2], "--n-cpu-moe", "8", *SPEC, *BASE[2:]]
    service = emit._locked_service("srv2_ornith", locked(argv))
    assert service["command"] == argv
