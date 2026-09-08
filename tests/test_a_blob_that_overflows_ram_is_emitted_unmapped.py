"""How a model is loaded is a property of the rig, so the rig's own scan picks it.

llama.cpp maps the weights by default, and under mmap every page is
file-backed — including the experts ``--n-cpu-moe`` put in host RAM. File-backed
means evictable, so a blob larger than the host's memory does not refuse and
does not OOM: the kernel drops expert pages to make room for the pages it is
reading, then reads them back on the next token, for as long as the server
serves. Nothing fails, so nothing catches it. Measured twice on this fleet:
821 MB/s of sustained NVMe reads *during decode* on 2026-08-25, and a 203 s
wake on 2026-09-08 (`records/measurements/wake-2026-09-08/`).

``--load-mode none`` is the cure and the whole difference: it reads the file
once, uploads what belongs on the card, frees that copy, and keeps only the
CPU-side experts as anonymous memory the kernel cannot take back. It is +63% on
a rig too tight for its blob and -12% on one with room (2026-08-25), so it is
not a default to flip — it is a per-rig derivation, which makes it the same
kind of number as ``--n-cpu-moe`` and belongs in the same place.

So the fit has two arms, and it names which one carried the model:

* the blob plus headroom fits available RAM -> mapped, nothing is emitted
* else the spilled experts plus headroom fit -> admitted, ``--load-mode none``
* else -> refused, because no loading mode makes a model fit a host this small

Before this spec the module had neither arm: it weighed the spilled experts
against ``MemAvailable`` with no headroom at all, which is exactly how KAT-Coder
passed onto srv1 (12.6 GiB of experts against 13 GiB available) and then took
203 s to wake behind a 16.9 GiB blob on a 15 GiB host.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, UnitError, fit, unit_for

WINDOW = 4096

GEOMETRY: dict[str, dict[str, Any]] = json.loads(
    (Path(__file__).parent / "fixtures" / "gguf_geometry.json").read_text(
        encoding="utf-8"
    )
)


def scanned(file: str) -> ModelSpec:
    """A spec whose sizes are the scan's, including the blob these arms weigh."""
    return ModelSpec(
        name=file[: -len(".gguf")],
        vram_gb=0.0,
        ram_gb=0.0,
        disk_gb=0.0,
        geometry=GEOMETRY[file],
    )


def rig(*, ram_gb: float, vram_mib: int = 6144) -> Scan:
    """One rig class — a 6 GiB card and six cores — varying only in RAM, so the
    arm a model takes is the only thing that moves between these tests."""
    return Scan.of(
        host="srv1",
        vram_mib=vram_mib,
        ram_gb=ram_gb,
        disk_free_gb=900.0,
        cores=6,
        threads=6,
        bandwidth_gbps=40.3,
    )


#: 12.3 GiB on disk; on a 6 GiB card it spills 29 blocks, 8.9 GiB of experts.
MOE = scanned("Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf")
#: 10.6 GiB on disk, 7.5 GiB of experts spilled on the same card.
GEMMA = scanned("gemma-4-26B-A4B-it-UD-IQ3_XXS.gguf")
#: 8.3 GiB on disk, 5.9 GiB spilled — the one model that fits srv1 mapped.
LITE = scanned("deepseek-coder-v2-16b.gguf")


def test_a_blob_that_overflows_ram_is_emitted_unmapped() -> None:
    """srv1 as it stands: 13 GiB available against a 12.3 GiB blob. The blob
    does not clear the headroom, the 8.9 GiB of experts do, so the model runs —
    with the mode that makes those experts unevictable."""
    unit = unit_for(rig(ram_gb=13.0), MOE, engine="llama.cpp", ctx_per_slot=WINDOW)
    assert unit.args["--load-mode"] == "none"


def test_a_blob_with_room_to_spare_is_left_mapped() -> None:
    """The same card and the same placement on a host with RAM: mmap is the
    engine's default, it is -12% to override it here, and a flag nobody needs
    is a number someone will later tune."""
    unit = unit_for(rig(ram_gb=48.0), MOE, engine="llama.cpp", ctx_per_slot=WINDOW)
    assert "--load-mode" not in unit.args


def test_the_arm_is_decided_with_headroom_not_on_the_bare_blob() -> None:
    """A blob that fits available RAM exactly is not a blob that fits: the page
    cache needs room to work and every other process on the host needs its own.
    12.3 GiB of weights into 12.5 GiB available is the unmapped arm."""
    unit = unit_for(rig(ram_gb=12.5), MOE, engine="llama.cpp", ctx_per_slot=WINDOW)
    assert unit.args["--load-mode"] == "none"


def test_a_model_that_fits_under_neither_mode_is_refused() -> None:
    """The KAT shape, and the regression this whole spec exists for: experts
    that clear bare `MemAvailable` while the blob behind them cannot fit the
    host at all. 8.9 + headroom > 10.0, so neither arm carries it."""
    with pytest.raises(UnitError) as raised:
        unit_for(rig(ram_gb=10.0), MOE, engine="llama.cpp", ctx_per_slot=WINDOW)
    why = str(raised.value)
    assert "12.3" in why, why
    assert "10.0" in why, why


def test_the_fit_states_which_mode_it_approved() -> None:
    """A fit that admitted a model on the unmapped arm approved a different
    launch from the one that fits mapped, and `emit --check` diffs argv: the
    mode is part of what was approved, not a decoration the unit adds later."""
    tight = fit(rig(ram_gb=13.0), MOE, ctx_per_slot=WINDOW)
    roomy = fit(rig(ram_gb=48.0), MOE, ctx_per_slot=WINDOW)
    assert tight.fits and roomy.fits
    assert tight.load_mode == "none"
    assert roomy.load_mode is None
    assert "load-mode none" in tight.why, tight.why


def test_every_model_on_the_tight_rig_is_judged_by_its_own_blob() -> None:
    """Not by the rig's reputation — srv1 is not "the unmapped rig".

    Its own two candidates on 13 GiB available: DeepSeek-Coder-V2-Lite's 8.3 GiB
    blob clears the headroom and maps, Qwen3.6-35B's 12.3 GiB does not and is
    read unmapped. One card, one moment, two arms. Gemma-4-26B sits between them
    at 10.6 GiB and maps, which is the point of weighing each blob rather than
    labelling the host.
    """
    tight = rig(ram_gb=13.0)
    lite = unit_for(tight, LITE, engine="llama.cpp", ctx_per_slot=WINDOW)
    gemma = unit_for(tight, GEMMA, engine="llama.cpp", ctx_per_slot=WINDOW)
    moe = unit_for(tight, MOE, engine="llama.cpp", ctx_per_slot=WINDOW)
    assert "--load-mode" not in lite.args
    assert "--load-mode" not in gemma.args
    assert moe.args["--load-mode"] == "none"


def test_vllm_is_never_handed_a_llama_cpp_loading_mode() -> None:
    """vLLM loads through its own path and would refuse the flag outright. The
    arms still decide whether the machine can hold the model; only llama.cpp is
    told how to load it."""
    served = replace(
        scanned("deepseek-coder-v2-16b.gguf"),
        hf_cache="/home/adaramir/.cache/huggingface",
    )
    unit = unit_for(
        rig(ram_gb=13.0, vram_mib=12288), served, engine="vllm", ctx_per_slot=WINDOW
    )
    assert "--load-mode" not in unit.args
