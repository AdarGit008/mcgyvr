"""The live ladder (owner, 2026-09-05): vLLM on srv2, llama.cpp on srv1, and
the flags a model needs that no scan can derive.

Measured by hand on 2026-09-05 (plan-e2e-live.md, "Spike results"): two vLLM
servers sit on srv2's 12 GB card together — the 7B AWQ at 7291 MiB and the 3B
AWQ beside it for 10869 MiB in all, 1043 MiB left — and srv1's Qwen3.6-35B
answered nothing but reasoning until ``--chat-template-kwargs`` turned thinking
off. Four things follow, each a check here:

* a ``vllm`` unit is a different process shape: the model id is positional,
  the weights come from the rig's HuggingFace cache and not from a GGUF under
  the weights directory, and the engine sizes its own cache from
  ``--gpu-memory-utilization`` — which the operator states, because #337 says
  that number is measured and never inherited;
* a model may carry ``serve_args``, appended verbatim to the argv, and both
  renderings carry them the same way;
* a source may pin its ``image``, because srv1's rows are only valid against a
  stated build (``okf/must-read/touching-rigs.md``) and the engine's default
  tag floats;
* the units on one host are summed against its free VRAM, because each unit
  fitting alone is exactly how a 12 GB card ends up asked for 13.
"""

from __future__ import annotations

import shlex
from typing import Any

import pytest
import yaml

from mcgyvr.config import parse
from mcgyvr.emit import EmitError, argv, render_command, render_compose
from mcgyvr.scan import Scan
from mcgyvr.serving import (
    ModelSpec,
    UnitError,
    declared_models,
    hold_together,
    unit_for,
    units_for,
)

#: The window these tests were written against, stated because nothing supplies
#: one any more. ``mcgyvr.serving.DEFAULT_CONTEXT`` was retired on 2026-09-06:
#: the window is what the run declares, so a test is a run and declares its own.
WINDOW = 4096

SEVEN_B = "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"
THREE_B = "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"
HF_CACHE = "/home/someone/.cache/huggingface"
VLLM_IMAGE = (
    "vllm/vllm-openai@sha256:"
    "ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52"
)
# The spike's card figures, in GiB: 7291 MiB alone, 10869 - 7291 beside it.
SEVEN_B_SPEC = ModelSpec(
    name=SEVEN_B,
    vram_gb=7.12,
    ram_gb=0.0,
    disk_gb=4.93,
    hf_cache=HF_CACHE,
    serve_args=("--gpu-memory-utilization", "0.68"),
)
THREE_B_SPEC = ModelSpec(
    name=THREE_B,
    vram_gb=3.49,
    ram_gb=0.0,
    disk_gb=1.95,
    hf_cache=HF_CACHE,
    serve_args=("--gpu-memory-utilization", "0.33"),
)


def rig(host: str, *, vram_mib: int = 12288, free_mib: int = 11911) -> Scan:
    scan = Scan.of(
        host=host,
        vram_mib=vram_mib,
        ram_gb=45.0,
        disk_free_gb=900.0,
        cores=10,
        threads=20,
        bandwidth_gbps=27.9,
    )
    gpu = scan.gpus[0]
    from dataclasses import replace

    return replace(
        scan, gpus=(replace(gpu, vram=replace(gpu.vram, free_mib=free_mib)),)
    )


def service_of(document: str) -> dict[str, Any]:
    return next(iter(yaml.safe_load(document)["services"].values()))


# --- a vLLM unit -----------------------------------------------------------


def test_a_vllm_unit_states_the_model_first_and_the_engines_own_flags() -> None:
    unit = unit_for(
        rig("srv2"),
        SEVEN_B_SPEC,
        engine="vllm",
        width=8,
        port=8002,
        ctx_per_slot=WINDOW,
    )
    parts = argv(unit)
    assert parts[0] == SEVEN_B, parts
    flags = dict(zip(parts[1::2], parts[2::2], strict=True))
    assert flags["--port"] == "8002"
    assert flags["--max-num-seqs"] == "8"
    assert flags["--max-model-len"] == str(WINDOW)
    assert flags["--gpu-memory-utilization"] == "0.68"
    assert "-ngl" not in flags and "-c" not in flags and "--model" not in flags


def test_a_vllm_unit_renders_a_bare_vllm_serve_command() -> None:
    unit = unit_for(
        rig("srv2"),
        SEVEN_B_SPEC,
        engine="vllm",
        width=8,
        port=8002,
        ctx_per_slot=WINDOW,
    )
    command = shlex.split(render_command(unit))
    assert command[:3] == ["vllm", "serve", SEVEN_B]
    assert command[3:] == list(argv(unit)[1:])


def test_a_vllm_unit_without_an_hf_cache_is_refused_by_name() -> None:
    spec = ModelSpec(name=SEVEN_B, vram_gb=7.12, ram_gb=0.0, disk_gb=4.93)
    with pytest.raises(UnitError, match="hf_cache"):
        unit_for(
            rig("srv2"), spec, engine="vllm", width=8, port=8002, ctx_per_slot=WINDOW
        )


def test_a_vllm_service_mounts_the_hf_cache_offline_with_host_ipc() -> None:
    unit = unit_for(
        rig("srv2"),
        SEVEN_B_SPEC,
        engine="vllm",
        width=8,
        port=8002,
        ctx_per_slot=WINDOW,
    )
    service = service_of(render_compose(unit))
    assert service["image"] == "vllm/vllm-openai:v0.26.0"
    assert service["volumes"] == [f"{HF_CACHE}:/root/.cache/huggingface:ro"]
    assert service["environment"]["HF_HUB_OFFLINE"] == "1"
    assert service["ipc"] == "host"
    assert service["command"] == list(argv(unit))


# --- serve_args --------------------------------------------------------------

THINKING_OFF = ("--chat-template-kwargs", '{"enable_thinking":false}')
DENSE = ModelSpec(
    name="qwen2.5-coder-3b",
    vram_gb=2.4,
    ram_gb=0.0,
    disk_gb=2.1,
    serve_args=THINKING_OFF,
)


def test_serve_args_reach_both_renderings_verbatim() -> None:
    unit = unit_for(
        rig("srv1", vram_mib=6144, free_mib=5727), DENSE, width=8, ctx_per_slot=WINDOW
    )
    parts = argv(unit)
    assert parts[-2:] == THINKING_OFF
    assert shlex.split(render_command(unit))[1:] == list(parts)
    assert service_of(render_compose(unit))["command"] == list(parts)


def test_a_serve_arg_with_whitespace_is_refused() -> None:
    spec = ModelSpec(
        name="qwen2.5-coder-3b",
        vram_gb=2.4,
        ram_gb=0.0,
        disk_gb=2.1,
        serve_args=("--chat-template-kwargs", '{"enable_thinking": false}'),
    )
    unit = unit_for(
        rig("srv1", vram_mib=6144, free_mib=5727), spec, width=8, ctx_per_slot=WINDOW
    )
    with pytest.raises(EmitError, match="whitespace"):
        argv(unit)


# --- the config carries all of it -------------------------------------------

LIVE = f"""
version: 1
sources:
  srv2_vllm_3b:
    base_url: "http://srv2:8001"
    api: openai
    engine: vllm
    image: "{VLLM_IMAGE}"
  srv2_vllm_7b:
    base_url: "http://srv2:8002"
    api: openai
    engine: vllm
    image: "{VLLM_IMAGE}"
models:
  {THREE_B}:
    vram_gb: 3.49
    disk_gb: 1.95
    hf_cache: "{HF_CACHE}"
    serve_args: ["--gpu-memory-utilization", "0.33"]
  {SEVEN_B}:
    vram_gb: 7.12
    disk_gb: 4.93
    hf_cache: "{HF_CACHE}"
    serve_args: ["--gpu-memory-utilization", "0.68"]
ladder:
  tiers:
    - name: local_qwen2.5-coder-3b
      source: srv2_vllm_3b
      model: "{THREE_B}"
      max_parallel: 8
    - name: local_qwen2.5-coder-7b
      source: srv2_vllm_7b
      model: "{SEVEN_B}"
      max_parallel: 8
"""


def test_declared_models_carry_serve_args_and_hf_cache() -> None:
    specs = declared_models(parse(LIVE))
    assert specs[SEVEN_B].hf_cache == HF_CACHE
    assert specs[SEVEN_B].serve_args == ("--gpu-memory-utilization", "0.68")
    assert specs[THREE_B].serve_args == ("--gpu-memory-utilization", "0.33")


def test_a_source_image_is_the_service_image() -> None:
    config = parse(LIVE)
    units = units_for(config, {"srv2": rig("srv2")}, specs=(), ctx_per_slot=WINDOW)
    for unit in units:
        tier = next(t for t in config.ladder.tiers if t.name == unit.rungs[0])
        assert unit.image == config.sources[tier.source].image
        assert unit.image is not None and "@sha256:" in unit.image
        assert service_of(render_compose(unit))["image"] == unit.image


def test_two_units_on_one_host_fit_it_together_at_the_spikes_numbers() -> None:
    scans = {"srv2": rig("srv2")}
    units = units_for(parse(LIVE), scans, specs=(), ctx_per_slot=WINDOW)
    assert sorted(unit.port for unit in units) == [8001, 8002]
    hold_together(units, scans)


def test_units_on_one_host_are_summed_against_its_free_vram() -> None:
    # Each alone fits an 11.9 GB card with room; together they do not.
    tight = LIVE.replace("vram_gb: 7.12", "vram_gb: 9.0")
    scans = {"srv2": rig("srv2")}
    units = units_for(parse(tight), scans, specs=(), ctx_per_slot=WINDOW)
    with pytest.raises(UnitError, match=r"together|sum"):
        hold_together(units, scans)
