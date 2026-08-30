"""A serving unit is one process: a host, a model, an engine and its arguments.

Rungs are not units. Several rungs may name one model on one host, and loading
its weights twice on one card is how a rig runs out of memory. The unit is what
gets started; the ladder only points at it.

Fit is measured against a scan, so a model that cannot sit in VRAM may still
fit a machine with the RAM to hold what spills.
"""

from __future__ import annotations

import pytest

from mcgyvr.config import Config, Ladder, Source, Tier
from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, UnitError, Width, fit, unit_for, units_for

SMALL = ModelSpec(name="qwen2.5-coder-3b", vram_gb=2.4, ram_gb=0.0, disk_gb=2.1)
MID = ModelSpec(name="qwen2.5-coder-14b", vram_gb=9.6, ram_gb=0.0, disk_gb=9.0)
MOE = ModelSpec(name="qwen3-coder-30b", vram_gb=5.0, ram_gb=13.6, disk_gb=18.6, moe=True)
HUGE = ModelSpec(name="glm-4.6-355b", vram_gb=24.0, ram_gb=180.0, disk_gb=220.0, moe=True)


def machine(host: str, *, vram_mib: int, ram_gb: float, free_gb: float, threads: int = 20) -> Scan:
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
        "desktop-1": machine("desktop-1", vram_mib=6144, ram_gb=48.0, free_gb=900.0, threads=10),
        "desktop-2": machine("desktop-2", vram_mib=12288, ram_gb=16.0, free_gb=120.0, threads=20),
    }


def config_for(*tiers: Tier) -> Config:
    return Config(
        version=1,
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
        },
        ladder=Ladder(tiers=tuple(tiers)),
    )


def test_a_unit_is_keyed_by_host_model_and_engine(scanned) -> None:
    first = unit_for(scanned["desktop-1"], MOE, engine="llama.cpp")
    second = unit_for(scanned["desktop-1"], MOE, engine="llama.cpp")
    assert first.key == second.key


def test_a_different_engine_is_a_different_unit(scanned) -> None:
    llama = unit_for(scanned["desktop-2"], MID, engine="llama.cpp")
    vllm = unit_for(scanned["desktop-2"], MID, engine="vllm")
    assert llama.key != vllm.key


def test_two_rungs_on_one_model_share_one_unit(scanned) -> None:
    config = config_for(
        Tier(name="local_a", source="d1", model="qwen3-coder-30b"),
        Tier(name="local_b", source="d1", model="qwen3-coder-30b", attempts=2),
    )
    assert len(units_for(config, scanned, specs=(MOE,))) == 1


def test_the_same_model_on_two_hosts_is_two_units(scanned) -> None:
    config = config_for(
        Tier(name="d1_moe", source="d1", model="qwen3-coder-30b"),
        Tier(name="d2_moe", source="d2", model="qwen3-coder-30b"),
    )
    assert len(units_for(config, scanned, specs=(MOE,))) == 2


def test_every_rung_resolves_to_the_unit_that_serves_it(scanned) -> None:
    config = config_for(
        Tier(name="local_a", source="d1", model="qwen3-coder-30b"),
        Tier(name="local_b", source="d1", model="qwen3-coder-30b"),
    )
    units = units_for(config, scanned, specs=(MOE,))
    assert {"local_a", "local_b"} == set(units[0].rungs)


def test_moe_offload_is_tuned_per_host_not_copied(scanned) -> None:
    one = unit_for(scanned["desktop-1"], MOE, engine="llama.cpp")
    two = unit_for(scanned["desktop-2"], MOE, engine="llama.cpp")
    assert one.args["--n-cpu-moe"] != two.args["--n-cpu-moe"]


def test_a_smaller_card_offloads_more_experts(scanned) -> None:
    one = unit_for(scanned["desktop-1"], MOE, engine="llama.cpp")
    two = unit_for(scanned["desktop-2"], MOE, engine="llama.cpp")
    assert int(one.args["--n-cpu-moe"]) > int(two.args["--n-cpu-moe"])


def test_threads_come_from_the_scan(scanned) -> None:
    unit = unit_for(scanned["desktop-2"], MOE, engine="llama.cpp")
    assert int(unit.args["-t"]) <= scanned["desktop-2"].cpu.threads


def test_fit_uses_ram_when_vram_alone_cannot_hold_the_model(scanned) -> None:
    assert fit(scanned["desktop-1"], MOE).fits is True


def test_a_dense_model_larger_than_vram_does_not_fit(scanned) -> None:
    assert fit(scanned["desktop-1"], MID).fits is False


def test_fit_refuses_a_model_that_needs_more_ram_than_the_host_has(scanned) -> None:
    assert fit(scanned["desktop-2"], HUGE).fits is False


def test_fit_refuses_a_model_that_needs_more_disk_than_is_free(scanned) -> None:
    assert fit(scanned["desktop-2"], HUGE).fits is False
    assert "disk" in fit(scanned["desktop-2"], HUGE).why


def test_vram_fit_keeps_its_headroom(scanned) -> None:
    assert fit(scanned["desktop-2"], SMALL).headroom_gb == 2.0


def test_fit_reads_free_vram_not_the_nameplate(scanned) -> None:
    busy = machine("desktop-2", vram_mib=12288, ram_gb=16.0, free_gb=120.0)
    busy = busy.with_vram_used(11286)
    assert fit(busy, MID).fits is False


def test_no_unit_is_emitted_for_an_unscanned_host(scanned) -> None:
    config = config_for(Tier(name="x", source="d1", model="qwen3-coder-30b"))
    with pytest.raises(UnitError, match="unscanned"):
        units_for(config, {}, specs=(MOE,))


def test_a_unit_carries_the_width_it_was_written_with(scanned) -> None:
    unit = unit_for(scanned["desktop-2"], SMALL, engine="llama.cpp", width=8)
    assert unit.width == Width(value=8, how="written")


def test_an_unstated_width_is_derived_from_the_scan_not_fixed_at_one(scanned) -> None:
    assert unit_for(scanned["desktop-2"], SMALL, engine="llama.cpp").width.value > 1


def test_a_unit_declares_no_queue_policy(scanned) -> None:
    unit = unit_for(scanned["desktop-1"], MOE, engine="llama.cpp")
    assert not hasattr(unit, "queue")
    assert not hasattr(unit, "schedule")
