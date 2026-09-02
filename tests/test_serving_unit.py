"""A serving unit is one process: a host, a model, an engine and its arguments.

Rungs are not units. Several rungs may name one model on one host, and loading
its weights twice on one card is how a rig runs out of memory. The unit is what
gets started; the ladder only points at it.

Fit is measured against a scan, so a model that cannot sit in VRAM may still
fit a machine with the RAM to hold what spills.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from mcgyvr.config import Config, Ladder, Source, Tier
from mcgyvr.scan import Scan
from mcgyvr.serving import (
    KV_GB_PER_SLOT,
    ModelSpec,
    UnitError,
    Width,
    fit,
    unit_for,
    units_for,
)

SMALL = ModelSpec(name="qwen2.5-coder-3b", vram_gb=2.4, ram_gb=0.0, disk_gb=2.1)
MID = ModelSpec(name="qwen2.5-coder-14b", vram_gb=9.6, ram_gb=0.0, disk_gb=9.0)
# blocks and expert_gb are the model's own geometry and there is no default
# for either: Qwen3-Coder-30B-A3B carries 48 blocks, and ~84% of an MoE file
# of this shape is expert tensors.
MOE = ModelSpec(
    name="qwen3-coder-30b",
    vram_gb=5.0,
    ram_gb=13.6,
    disk_gb=18.6,
    moe=True,
    blocks=48,
    expert_gb=15.6,
)
HUGE = ModelSpec(
    name="glm-4.6-355b",
    vram_gb=24.0,
    ram_gb=180.0,
    disk_gb=220.0,
    moe=True,
    blocks=92,
    expert_gb=200.0,
)


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
def scanned() -> dict[str, Scan]:
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


def test_a_unit_is_keyed_by_host_model_and_engine(scanned: dict[str, Scan]) -> None:
    first = unit_for(scanned["desktop-1"], MOE, engine="llama.cpp")
    second = unit_for(scanned["desktop-1"], MOE, engine="llama.cpp")
    assert first.key == second.key


def test_a_different_engine_is_a_different_unit(scanned: dict[str, Scan]) -> None:
    llama = unit_for(scanned["desktop-2"], MID, engine="llama.cpp")
    vllm = unit_for(scanned["desktop-2"], MID, engine="vllm")
    assert llama.key != vllm.key


def test_two_rungs_on_one_model_share_one_unit(scanned: dict[str, Scan]) -> None:
    config = config_for(
        Tier(name="local_a", source="d1", model="qwen3-coder-30b"),
        Tier(name="local_b", source="d1", model="qwen3-coder-30b", attempts=2),
    )
    assert len(units_for(config, scanned, specs=(MOE,))) == 1


def test_the_same_model_on_two_hosts_is_two_units(scanned: dict[str, Scan]) -> None:
    config = config_for(
        Tier(name="d1_moe", source="d1", model="qwen3-coder-30b"),
        Tier(name="d2_moe", source="d2", model="qwen3-coder-30b"),
    )
    assert len(units_for(config, scanned, specs=(MOE,))) == 2


def test_every_rung_resolves_to_the_unit_that_serves_it(
    scanned: dict[str, Scan],
) -> None:
    config = config_for(
        Tier(name="local_a", source="d1", model="qwen3-coder-30b"),
        Tier(name="local_b", source="d1", model="qwen3-coder-30b"),
    )
    units = units_for(config, scanned, specs=(MOE,))
    assert {"local_a", "local_b"} == set(units[0].rungs)


def test_moe_offload_is_tuned_per_host_not_copied(scanned: dict[str, Scan]) -> None:
    one = unit_for(scanned["desktop-1"], MOE, engine="llama.cpp")
    two = unit_for(scanned["desktop-2"], MOE, engine="llama.cpp")
    assert one.args["--n-cpu-moe"] != two.args["--n-cpu-moe"]


def test_a_smaller_card_offloads_more_experts(scanned: dict[str, Scan]) -> None:
    one = unit_for(scanned["desktop-1"], MOE, engine="llama.cpp")
    two = unit_for(scanned["desktop-2"], MOE, engine="llama.cpp")
    assert int(one.args["--n-cpu-moe"]) > int(two.args["--n-cpu-moe"])


def test_threads_come_from_the_scan(scanned: dict[str, Scan]) -> None:
    unit = unit_for(scanned["desktop-2"], MOE, engine="llama.cpp")
    cpu = scanned["desktop-2"].cpu
    assert cpu is not None
    assert int(unit.args["-t"]) <= cpu.threads


def test_fit_uses_ram_when_vram_alone_cannot_hold_the_model(
    scanned: dict[str, Scan],
) -> None:
    assert fit(scanned["desktop-1"], MOE).fits is True


def test_a_dense_model_larger_than_vram_does_not_fit(scanned: dict[str, Scan]) -> None:
    assert fit(scanned["desktop-1"], MID).fits is False


def test_fit_refuses_a_model_that_needs_more_ram_than_the_host_has(
    scanned: dict[str, Scan],
) -> None:
    assert fit(scanned["desktop-2"], HUGE).fits is False


def test_fit_refuses_a_model_that_needs_more_disk_than_is_free(
    scanned: dict[str, Scan],
) -> None:
    assert fit(scanned["desktop-2"], HUGE).fits is False
    assert "disk" in fit(scanned["desktop-2"], HUGE).why


def test_vram_fit_keeps_its_headroom(scanned: dict[str, Scan]) -> None:
    assert fit(scanned["desktop-2"], SMALL).headroom_gb == 2.0


def test_fit_reads_free_vram_not_the_nameplate(scanned: dict[str, Scan]) -> None:
    busy = machine("desktop-2", vram_mib=12288, ram_gb=16.0, free_gb=120.0)
    busy = busy.with_vram_used(11286)
    assert fit(busy, MID).fits is False


def test_no_unit_is_emitted_for_an_unscanned_host(scanned: dict[str, Scan]) -> None:
    config = config_for(Tier(name="x", source="d1", model="qwen3-coder-30b"))
    with pytest.raises(UnitError, match="unscanned"):
        units_for(config, {}, specs=(MOE,))


def test_a_unit_carries_the_width_it_was_written_with(scanned: dict[str, Scan]) -> None:
    unit = unit_for(scanned["desktop-2"], SMALL, engine="llama.cpp", width=8)
    assert unit.width == Width(value=8, how="written")


def test_an_unstated_width_is_derived_from_the_scan_not_fixed_at_one(
    scanned: dict[str, Scan],
) -> None:
    assert unit_for(scanned["desktop-2"], SMALL, engine="llama.cpp").width.value > 1


def test_a_unit_declares_no_queue_policy(scanned: dict[str, Scan]) -> None:
    unit = unit_for(scanned["desktop-1"], MOE, engine="llama.cpp")
    assert not hasattr(unit, "queue")
    assert not hasattr(unit, "schedule")


def test_an_moe_that_fits_the_card_offloads_nothing(scanned: dict[str, Scan]) -> None:
    """``--n-cpu-moe 0`` is a flag that does nothing, printed in a file a person reads.

    The offload count is derived, so a big enough card legitimately produces
    zero. Emitting it anyway teaches the reader that this rig offloads experts
    when it does not, and the first thing they will do is tune a number that
    was never in play.
    """
    roomy = machine("desktop-3", vram_mib=49152, ram_gb=128.0, free_gb=900.0)
    assert "--n-cpu-moe" not in unit_for(roomy, MOE, engine="llama.cpp").args


def test_a_unit_listens_where_the_ladder_expects_to_reach_it(
    scanned: dict[str, Scan],
) -> None:
    """The source's URL is a promise about where the rung answers.

    A unit built without it starts on the engine's default port, so a ladder
    naming two ports on one host emits two servers that both take the first
    one. The config already holds the answer; the unit has to carry it.
    """
    config = config_for(
        Tier(name="fast", source="d1", model="qwen2.5-coder-3b"),
        Tier(name="smart", source="d1b", model="qwen3-coder-30b"),
    )
    units = units_for(config, scanned, specs=(SMALL, MOE))
    assert sorted(unit.port for unit in units) == [8080, 8081]


def test_a_unit_built_without_a_ladder_takes_the_engine_default(
    scanned: dict[str, Scan],
) -> None:
    assert unit_for(scanned["desktop-2"], SMALL, engine="llama.cpp").port == 8080


# deepseek-coder-v2:16b as the shipped capability table describes it -- a 9.4 GB
# working set over 8.9 GB of weights -- with the block count the table does not
# carry supplied, and with the RAM figure `mcgyvr emit` used to build for it:
# nothing, because `weights - working` was negative and clamped to zero.
SPILLER = ModelSpec(
    name="deepseek-coder-v2:16b",
    vram_gb=9.4,
    ram_gb=0.0,
    disk_gb=8.9,
    moe=True,
    blocks=27,
    expert_gb=7.5,
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
    sized = fit(cramped, SPILLER)
    assert sized.fits is False
    assert "RAM" in sized.why
    with pytest.raises(UnitError):
        unit_for(cramped, SPILLER, engine="llama.cpp")


def test_an_moe_whose_block_count_is_unknown_is_refused_not_assumed(
    scanned: dict[str, Scan],
) -> None:
    """`--n-cpu-moe` counts blocks, so a model that has not said how many is unsized.

    Every expert figure is the mass divided by that count, and the count is
    per model: gpt-oss-20b has 24 where the sweep's Qwen3 pair has 48. Borrow
    one for the other and each block is priced at half what it costs, so the
    offload reports as placed and does not fit. A refusal is an exit-3 path an
    operator can act on -- the message says the table has no block count --
    and a guess is a compose file that fails on the rig.
    """
    unknown = replace(MOE, blocks=None)
    sized = fit(scanned["desktop-1"], unknown)
    assert sized.fits is False
    assert "block" in sized.why


def test_two_sources_on_one_host_are_two_processes(scanned: dict[str, Scan]) -> None:
    """Two ports are two servers, whatever else the two rungs have in common.

    A fast lane on 8080 and a careful one on 8081, same host and same model,
    are two `llama-server` processes because that is what their URLs promise.
    Keyed without the port they collapse into one unit holding the first port
    and both rung names: one container is emitted, nothing listens on 8081,
    and the rung bound to it is dead. The caller's port-contention check does
    not fire either, because the two base URLs genuinely differ.
    """
    config = config_for(
        Tier(name="fastlane", source="d1", model="qwen3-coder-30b"),
        Tier(name="careful", source="d1b", model="qwen3-coder-30b"),
    )
    units = units_for(config, scanned, specs=(MOE,))
    assert sorted(unit.port for unit in units) == [8080, 8081]
    assert sorted(unit.rungs for unit in units) == [("careful",), ("fastlane",)]


def test_the_derived_width_does_not_spend_the_headroom_the_fit_held_back(
    scanned: dict[str, Scan],
) -> None:
    """One unit cannot both reserve the headroom and hand it out as slots.

    The fit reports "2.0 GB headroom held back" and the width was then derived
    from free VRAM minus the weights alone -- so on a 12 GB card the reserve
    came straight back as slots, at this module's own KV price. Whichever half
    is right, they cannot both be, and the disagreement resolves on the rig as
    an OOM under load rather than as a number anyone reads.
    """
    unit = unit_for(scanned["desktop-2"], MID, engine="llama.cpp")
    free_vram_gb = 12288 / 1024
    spare = free_vram_gb - MID.vram_gb - unit.fit.headroom_gb
    assert unit.width.value * KV_GB_PER_SLOT <= spare


def test_a_model_id_with_a_slash_mounts_the_directory_the_scan_measured(
    scanned: dict[str, Scan],
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
    unit = unit_for(scanned["desktop-2"], nested, engine="llama.cpp")
    disk = scanned["desktop-2"].disk
    assert disk is not None
    assert unit.weights_dir == disk.path
    assert "/" not in unit.weights.name
