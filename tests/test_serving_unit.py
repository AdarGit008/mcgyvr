"""A serving unit is one process: a host, a model, an engine and its arguments.

Rungs are not units. Several rungs may name one model on one host, and loading
its weights twice on one card is how a rig runs out of memory. The unit is what
gets started; the ladder only points at it.

Fit is measured against a scan, so a model that cannot sit in VRAM may still
fit a machine with the RAM to hold what spills. What spills is read off the
model's own GGUF geometry (``tests/fixtures/gguf_geometry.json``, one
``ggufscan`` row per file), never off a constant of this module's.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import Config, Ladder, Source, Tier
from mcgyvr.scan import Scan
from mcgyvr.serving import (
    DEFAULT_UBATCH,
    ModelSpec,
    UnitError,
    Width,
    _placement,
    fit,
    unit_for,
    units_for,
)

#: The window these tests were written against, stated because nothing supplies
#: one any more. ``mcgyvr.serving.DEFAULT_CONTEXT`` was retired on 2026-09-06:
#: the window is what the run declares, so a test is a run and declares its own.
WINDOW = 4096

GEOMETRY: dict[str, dict[str, Any]] = json.loads(
    (Path(__file__).parent / "fixtures" / "gguf_geometry.json").read_text(
        encoding="utf-8"
    )
)


def scanned(file: str, *, ram_gb: float = 0.0) -> ModelSpec:
    """A spec whose bytes are the scan's: the name is the file's, the sizes
    come off the row, and nothing scalar is stated for the law to disagree
    with."""
    return ModelSpec(
        name=file[: -len(".gguf")],
        vram_gb=0.0,
        ram_gb=ram_gb,
        disk_gb=0.0,
        geometry=GEOMETRY[file],
    )


SMALL = ModelSpec(name="qwen2.5-coder-3b", vram_gb=2.4, ram_gb=0.0, disk_gb=2.1)
MID = ModelSpec(name="qwen2.5-coder-14b", vram_gb=9.6, ram_gb=0.0, disk_gb=9.0)
# Qwen3.6-35B-A3B at IQ3_XXS: 12.3 GiB on disk, 40 placeable expert blocks and
# 30 recurrent ones, so a slot costs recurrent state as well as cache.
MOE = scanned("Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf")
# Qwen3-Next-80B-A3B at Q3_K_M: 35.7 GiB on disk. On a 12 GB card the experts
# it spills are more than a 16 GB host has.
HUGE = scanned("Qwen3-Next-80B-A3B-Instruct-Q3_K_M.gguf")
# deepseek-coder-v2:16b at Q4_0: 8.3 GiB, 26 placeable blocks of 297 MiB each,
# every layer caching a 192-wide key against a 128-wide value.
SPILLER = scanned("deepseek-coder-v2-16b.gguf")


def machine(
    host: str, *, vram_mib: int, ram_gb: float, free_gb: float, threads: int = 20
) -> Scan:
    return Scan.of(
        host=host,
        vram_mib=vram_mib,
        ram_gb=ram_gb,
        disk_free_gb=free_gb,
        cores=threads // 2,
        threads=threads,
        bandwidth_gbps=41.2,
    )


@pytest.fixture
def scans() -> dict[str, Scan]:
    return {
        "desktop-1": machine(
            "desktop-1", vram_mib=6144, ram_gb=48.0, free_gb=900.0, threads=10
        ),
        "desktop-2": machine(
            "desktop-2", vram_mib=12288, ram_gb=16.0, free_gb=120.0, threads=20
        ),
    }


def config_for(*tiers: Tier) -> Config:
    return Config(
        path=None,
        data={},
        sources={
            "d1": Source(
                name="d1",
                base_url="http://desktop-1:8080",
                api="openai",
                max_parallel=1,
                api_key_env=None,
            ),
            "d2": Source(
                name="d2",
                base_url="http://desktop-2:8080",
                api="openai",
                max_parallel=1,
                api_key_env=None,
            ),
            "d1b": Source(
                name="d1b",
                base_url="http://desktop-1:8081",
                api="openai",
                max_parallel=1,
                api_key_env=None,
            ),
        },
        ladder=Ladder(tiers=tuple(tiers)),
    )


def test_a_unit_is_keyed_by_host_model_and_engine(scans: dict[str, Scan]) -> None:
    first = unit_for(scans["desktop-1"], MOE, engine="llama.cpp", ctx_per_slot=WINDOW)
    second = unit_for(scans["desktop-1"], MOE, engine="llama.cpp", ctx_per_slot=WINDOW)
    assert first.key == second.key


def test_a_different_engine_is_a_different_unit(scans: dict[str, Scan]) -> None:
    llama = unit_for(scans["desktop-2"], MID, engine="llama.cpp", ctx_per_slot=WINDOW)
    served = replace(MID, hf_cache="/home/someone/.cache/huggingface")
    vllm = unit_for(scans["desktop-2"], served, engine="vllm", ctx_per_slot=WINDOW)
    assert llama.key != vllm.key


def test_two_rungs_on_one_model_share_one_unit(scans: dict[str, Scan]) -> None:
    config = config_for(
        Tier(name="local_a", source="d1", model=MOE.name),
        Tier(name="local_b", source="d1", model=MOE.name, attempts=2),
    )
    assert len(units_for(config, scans, specs=(MOE,), ctx_per_slot=WINDOW)) == 1


def test_the_same_model_on_two_hosts_is_two_units(scans: dict[str, Scan]) -> None:
    config = config_for(
        Tier(name="d1_moe", source="d1", model=MOE.name),
        Tier(name="d2_moe", source="d2", model=MOE.name),
    )
    assert len(units_for(config, scans, specs=(MOE,), ctx_per_slot=WINDOW)) == 2


def test_every_rung_resolves_to_the_unit_that_serves_it(
    scans: dict[str, Scan],
) -> None:
    config = config_for(
        Tier(name="local_a", source="d1", model=MOE.name),
        Tier(name="local_b", source="d1", model=MOE.name),
    )
    units = units_for(config, scans, specs=(MOE,), ctx_per_slot=WINDOW)
    assert {"local_a", "local_b"} == set(units[0].rungs)


def test_moe_offload_is_tuned_per_host_not_copied(scans: dict[str, Scan]) -> None:
    one = unit_for(scans["desktop-1"], MOE, engine="llama.cpp", ctx_per_slot=WINDOW)
    two = unit_for(scans["desktop-2"], MOE, engine="llama.cpp", ctx_per_slot=WINDOW)
    assert one.args["--n-cpu-moe"] != two.args["--n-cpu-moe"]


def test_a_smaller_card_offloads_more_experts(scans: dict[str, Scan]) -> None:
    one = unit_for(scans["desktop-1"], MOE, engine="llama.cpp", ctx_per_slot=WINDOW)
    two = unit_for(scans["desktop-2"], MOE, engine="llama.cpp", ctx_per_slot=WINDOW)
    assert int(one.args["--n-cpu-moe"]) > int(two.args["--n-cpu-moe"])


def test_threads_come_from_the_scan(scans: dict[str, Scan]) -> None:
    unit = unit_for(scans["desktop-2"], MOE, engine="llama.cpp", ctx_per_slot=WINDOW)
    cpu = scans["desktop-2"].cpu
    assert cpu is not None
    assert int(unit.args["-t"]) <= cpu.threads


def test_fit_uses_ram_when_vram_alone_cannot_hold_the_model(
    scans: dict[str, Scan],
) -> None:
    assert fit(scans["desktop-1"], MOE, ctx_per_slot=WINDOW).fits is True


def test_a_dense_model_larger_than_vram_does_not_fit(scans: dict[str, Scan]) -> None:
    assert fit(scans["desktop-1"], MID, ctx_per_slot=WINDOW).fits is False


def test_fit_refuses_a_model_that_needs_more_ram_than_the_host_has(
    scans: dict[str, Scan],
) -> None:
    sized = fit(scans["desktop-2"], HUGE, ctx_per_slot=WINDOW)
    assert sized.fits is False
    assert "RAM" in sized.why


def test_fit_refuses_a_model_that_needs_more_disk_than_is_free() -> None:
    cramped = machine("desktop-5", vram_mib=12288, ram_gb=64.0, free_gb=10.0)
    sized = fit(cramped, HUGE, ctx_per_slot=WINDOW)
    assert sized.fits is False
    assert "disk" in sized.why


def test_vram_fit_keeps_its_headroom(scans: dict[str, Scan]) -> None:
    """A scalar spec is held back from by the proposal's headroom."""
    assert fit(scans["desktop-2"], SMALL, ctx_per_slot=WINDOW).headroom_gb == 2.0


def test_a_scanned_fit_reports_the_scratch_allowance_it_carries(
    scans: dict[str, Scan],
) -> None:
    """With a geometry, the one allowance is inside the card figure, not on top.

    Everything else in that figure is read from the header, so what the fit
    "held back" is the compute scratch and the unnamed allocation the header
    cannot supply -- ``vramfit.SCRATCH_AND_CONTEXT_MIB`` -- and it says so
    rather than reporting a reserve it did not take.
    """
    from mcgyvr.serving import vramfit

    sized = fit(scans["desktop-2"], MOE, ctx_per_slot=WINDOW)
    assert sized.fits is True
    assert sized.headroom_gb == vramfit.SCRATCH_AND_CONTEXT_MIB / 1024


def test_fit_reads_free_vram_not_the_nameplate(scans: dict[str, Scan]) -> None:
    busy = machine("desktop-2", vram_mib=12288, ram_gb=16.0, free_gb=120.0)
    busy = busy.with_vram_used(11286)
    assert fit(busy, MID, ctx_per_slot=WINDOW).fits is False


def test_no_unit_is_emitted_for_an_unscanned_host(scans: dict[str, Scan]) -> None:
    config = config_for(Tier(name="x", source="d1", model=MOE.name))
    with pytest.raises(UnitError, match="unscanned"):
        units_for(config, {}, specs=(MOE,), ctx_per_slot=WINDOW)


def test_a_unit_carries_the_width_it_was_written_with(scans: dict[str, Scan]) -> None:
    unit = unit_for(
        scans["desktop-2"], SMALL, engine="llama.cpp", width=8, ctx_per_slot=WINDOW
    )
    assert unit.width == Width(value=8, how="written")


def test_an_unstated_width_is_derived_from_the_card_and_the_header() -> None:
    """A roomy card serves many slots, and the number is the cache law's.

    A default of 1 is a claim -- that this rig serves one request at a time --
    and #366 found 32 slots on a 12 GB card reaching 254 tok/s against ~67
    single-stream. What bounds the number is the cache and state the header
    prices per slot against what the card has left, so a 48 GB card holding
    an 8 GB model is not one slot wide.
    """
    roomy = machine("desktop-3", vram_mib=49152, ram_gb=128.0, free_gb=900.0)
    unit = unit_for(roomy, SPILLER, engine="llama.cpp", ctx_per_slot=WINDOW)
    assert unit.width.how == "derived"
    assert unit.width.value > 1


def test_a_spec_without_a_geometry_is_one_slot_wide_and_says_so(
    scans: dict[str, Scan],
) -> None:
    """Nothing here can price a second slot for a model nobody scanned.

    The per-slot cost is the cache law's and the law reads the header. The
    constant that used to stand in for it was measured on one family and
    applied to every other, which is the shape of error this module retired;
    so a scalar spec gets one slot, labelled as the default it is, and an
    operator widens it by writing ``max_parallel`` or by scanning the file.
    """
    unit = unit_for(scans["desktop-2"], SMALL, engine="llama.cpp", ctx_per_slot=WINDOW)
    assert unit.width == Width(value=1, how="default")


def test_a_unit_declares_no_queue_policy(scans: dict[str, Scan]) -> None:
    unit = unit_for(scans["desktop-1"], MOE, engine="llama.cpp", ctx_per_slot=WINDOW)
    assert not hasattr(unit, "queue")
    assert not hasattr(unit, "schedule")


def test_an_moe_that_fits_the_card_offloads_nothing() -> None:
    """``--n-cpu-moe 0`` is a flag that does nothing, printed in a file a person reads.

    The offload count is derived, so a big enough card legitimately produces
    zero. Emitting it anyway teaches the reader that this rig offloads experts
    when it does not, and the first thing they will do is tune a number that
    was never in play.
    """
    roomy = machine("desktop-3", vram_mib=49152, ram_gb=128.0, free_gb=900.0)
    assert (
        "--n-cpu-moe"
        not in unit_for(roomy, MOE, engine="llama.cpp", ctx_per_slot=WINDOW).args
    )


def test_a_unit_listens_where_the_ladder_expects_to_reach_it(
    scans: dict[str, Scan],
) -> None:
    """The source's URL is a promise about where the rung answers.

    A unit built without it starts on the engine's default port, so a ladder
    naming two ports on one host emits two servers that both take the first
    one. The config already holds the answer; the unit has to carry it.
    """
    config = config_for(
        Tier(name="fast", source="d1", model="qwen2.5-coder-3b"),
        Tier(name="smart", source="d1b", model=MOE.name),
    )
    units = units_for(config, scans, specs=(SMALL, MOE), ctx_per_slot=WINDOW)
    assert sorted(unit.port for unit in units) == [8080, 8081]


def test_a_unit_built_without_a_ladder_takes_the_engine_default(
    scans: dict[str, Scan],
) -> None:
    assert (
        unit_for(
            scans["desktop-2"], SMALL, engine="llama.cpp", ctx_per_slot=WINDOW
        ).port
        == 8080
    )


def test_an_moe_is_refused_when_the_experts_it_spills_exceed_free_ram() -> None:
    """An offload is a demand on memory, so a fit has to ask memory about it.

    The only RAM question this module used to ask was about a number the
    caller declared, and the caller declared zero -- so a 6 GB card with a
    gigabyte of memory free was told it could serve a model whose experts are
    five gigabytes, and the emitted `--n-cpu-moe` put them there. The compose
    file was written, the command exited zero, and the rig swapped.

    The number checked here is the one the argv will carry, not a second
    opinion: whatever `unit_for` offloads is what memory is asked to hold.
    """
    cramped = machine("desktop-4", vram_mib=6144, ram_gb=1.0, free_gb=900.0)
    sized = fit(cramped, SPILLER, ctx_per_slot=WINDOW)
    assert sized.fits is False
    assert "RAM" in sized.why
    with pytest.raises(UnitError):
        unit_for(cramped, SPILLER, engine="llama.cpp", ctx_per_slot=WINDOW)


def test_an_moe_without_its_geometry_is_refused_and_told_where_to_scan(
    scans: dict[str, Scan],
) -> None:
    """`--n-cpu-moe` moves whole blocks, and a block weighs what its tensors weigh.

    That figure is in the tensor table and nowhere else: gpt-oss-20b carries
    24 blocks at 404 MiB, Qwen3.6-35B forty at 262 and 300, and neither a
    name nor a parameter count nor a file size says which. A refusal is an
    exit-3 path an operator can act on -- the message names the scanner and
    the config key -- and a guess is a compose file that fails on the rig.
    """
    unknown = replace(MOE, geometry=None)
    sized = fit(scans["desktop-1"], unknown, ctx_per_slot=WINDOW)
    assert sized.fits is False
    assert "ggufscan" in sized.why
    assert "geometry_json" in sized.why
    with pytest.raises(UnitError, match="ggufscan"):
        unit_for(scans["desktop-1"], unknown, engine="llama.cpp", ctx_per_slot=WINDOW)


def test_two_sources_on_one_host_are_two_processes(scans: dict[str, Scan]) -> None:
    """Two ports are two servers, whatever else the two rungs have in common.

    A fast lane on 8080 and a careful one on 8081, same host and same model,
    are two `llama-server` processes because that is what their URLs promise.
    Keyed without the port they collapse into one unit holding the first port
    and both rung names: one container is emitted, nothing listens on 8081,
    and the rung bound to it is dead. The caller's port-contention check does
    not fire either, because the two base URLs genuinely differ.
    """
    config = config_for(
        Tier(name="fastlane", source="d1", model=MOE.name),
        Tier(name="careful", source="d1b", model=MOE.name),
    )
    units = units_for(config, scans, specs=(MOE,), ctx_per_slot=WINDOW)
    assert sorted(unit.port for unit in units) == [8080, 8081]
    assert sorted(unit.rungs for unit in units) == [("careful",), ("fastlane",)]


def test_the_derived_width_stops_before_a_slot_costs_an_expert_block(
    scans: dict[str, Scan],
) -> None:
    """As wide as the card allows without moving one more block off it.

    A slot is cache and recurrent state on the card, and the floor is the
    lowest ``--n-cpu-moe`` whose experts fit beside them. The derived width is
    the largest one whose floor is still the floor at one slot: the next slot
    would push an expert block to the CPU, which is paid on every request,
    and that trade is an operator's to write down rather than this module's
    to make silently.
    """
    unit = unit_for(
        scans["desktop-2"], SPILLER, engine="llama.cpp", ctx_per_slot=WINDOW
    )
    free_bytes = 12288 << 20
    at_one = _placement(SPILLER, free_bytes, 1, ctx_per_slot=WINDOW)
    at_width = _placement(SPILLER, free_bytes, unit.width.value, ctx_per_slot=WINDOW)
    one_wider = _placement(
        SPILLER, free_bytes, unit.width.value + 1, ctx_per_slot=WINDOW
    )
    assert unit.width.how == "derived"
    assert at_width.n_cpu_moe == at_one.n_cpu_moe
    assert one_wider.n_cpu_moe > at_one.n_cpu_moe, (
        f"width {unit.width.value} should be the last that keeps the floor at "
        f"{at_one.n_cpu_moe}; one wider gave {one_wider.n_cpu_moe}"
    )
    assert at_width.vram_gb <= free_bytes / 1024**3, (
        "the card figure at the derived width, scratch allowance included, "
        "must fit the free VRAM the fit was checked against"
    )


def test_the_argv_states_exactly_what_the_cache_law_was_fed(
    scans: dict[str, Scan],
) -> None:
    """``-c`` is the total across slots and ``-ub`` the micro-batch, both stated.

    The law sized the cache at ``WINDOW`` per slot times the slot
    count and padded the sliding window against ``DEFAULT_UBATCH``. An argv
    that emitted a per-slot ``-c`` would allocate a cache one slot's worth of
    the size that was checked, and one that left ``-ub`` to the engine would
    be sized for a default the law had to guess.
    """
    unit = unit_for(scans["desktop-1"], MOE, engine="llama.cpp", ctx_per_slot=WINDOW)
    assert unit.args["--parallel"] == str(unit.width.value)
    assert unit.args["-c"] == str(WINDOW * unit.width.value)
    assert unit.args["-ub"] == str(DEFAULT_UBATCH)
    assert unit.args["-b"] == str(DEFAULT_UBATCH)


def test_a_written_width_recomputes_the_floor_at_that_width(
    scans: dict[str, Scan],
) -> None:
    """``--parallel`` and ``--n-cpu-moe`` are sized together or not at all."""
    unit = unit_for(
        scans["desktop-2"], SPILLER, engine="llama.cpp", width=8, ctx_per_slot=WINDOW
    )
    placed = _placement(SPILLER, 12288 << 20, 8, ctx_per_slot=WINDOW)
    assert unit.args["-c"] == str(WINDOW * 8)
    assert placed.n_cpu_moe > 0
    assert unit.args["--n-cpu-moe"] == str(placed.n_cpu_moe)


def test_a_model_id_with_a_slash_mounts_the_directory_the_scan_measured(
    scans: dict[str, Scan],
) -> None:
    """A model id is a name here, not a path into the weights directory.

    `Qwen/Qwen2.5-Coder-7B-Instruct-AWQ` spelled into the file name puts the
    weights one directory down, so what gets bind-mounted is `/srv/weights/Qwen`
    while the disk check was about `/srv/weights`. If that subdirectory does not
    exist Docker creates it -- empty and root-owned -- and the server fails at
    load against a mount the operator has to go and delete by hand.
    """
    nested = ModelSpec(
        name="Qwen/Qwen2.5-Coder-7B-Instruct-AWQ",
        vram_gb=5.29,
        ram_gb=0.0,
        disk_gb=5.29,
    )
    unit = unit_for(scans["desktop-2"], nested, engine="llama.cpp", ctx_per_slot=WINDOW)
    disk = scans["desktop-2"].disk
    assert disk is not None
    assert unit.weights_dir == disk.path
    assert "/" not in unit.weights.name
