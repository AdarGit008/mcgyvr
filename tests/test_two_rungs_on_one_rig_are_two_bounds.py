"""Rung != rig: two rungs co-resident on one machine are two server processes
with two bounds, and the ladder counts them as two.

The live ladder puts two vLLM servers on srv2 — the 3B on :8001 and the 7B
on :8002 — behind two sources. Capacity keys its slots by the source URL and
the rung, never by the host, so a slot held on one does not count against the
other; ``units_for`` sees two processes; ``pool`` lists two rungs. This file
pins all three, because "one host, one rung" is the assumption a co-resident
ladder breaks and nothing else asserted it.
"""

from __future__ import annotations

from pathlib import Path

from mcgyvr.capacity import Capacity, _slot_stem
from mcgyvr.config import parse
from mcgyvr.pool import source_map
from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, units_for

#: The window these tests use, stated because ``mcgyvr.serving`` supplies no
#: default: the window is what the run declares, so a test is a run and declares
#: its own.
WINDOW = 4096

CO_RESIDENT = """\
units:
  local_3b:
    address: http://srv2:8001
    model: Qwen/Qwen2.5-Coder-3B-Instruct-AWQ
    rig: srv2_vllm_3b
    width: 8
    engine: vllm
  local_7b:
    address: http://srv2:8002
    model: Qwen/Qwen2.5-Coder-7B-Instruct-AWQ
    rig: srv2_vllm_7b
    width: 8
    engine: vllm
ladder:
- local_3b
- local_7b
"""
HF = "/home/someone/.cache/huggingface"


def test_two_sources_on_one_host_are_two_slot_files() -> None:
    assert _slot_stem("http://srv2:8001", "local_3b") != _slot_stem(
        "http://srv2:8002", "local_7b"
    )


def test_a_slot_held_on_one_rung_does_not_count_on_the_other(tmp_path: Path) -> None:
    capacity = Capacity.of(parse(CO_RESIDENT), root=tmp_path)
    assert capacity.limit("local_3b") == 8
    assert capacity.limit("local_7b") == 8
    with capacity.hold("local_3b"):
        assert capacity.in_flight("local_3b") == 1
        assert capacity.in_flight("local_7b") == 0


def test_the_pool_lists_both_rungs_of_one_host() -> None:
    pool = source_map(parse(CO_RESIDENT))
    assert [rung.name for rung in pool.rungs] == ["local_3b", "local_7b"]


def test_the_ladder_implies_two_processes_on_the_one_host() -> None:
    scan = Scan.of(
        host="srv2",
        vram_mib=12288,
        ram_gb=45.0,
        disk_free_gb=80.0,
        cores=10,
        threads=20,
        bandwidth_gbps=27.9,
    )
    specs = (
        ModelSpec(
            "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ",
            3.49,
            0.0,
            1.95,
            hf_cache=HF,
            kv_cache_dtype_k="auto",
        ),
        ModelSpec(
            "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ",
            7.12,
            0.0,
            4.93,
            hf_cache=HF,
            kv_cache_dtype_k="auto",
        ),
    )
    units = units_for(
        parse(CO_RESIDENT), {"srv2": scan}, specs=specs, ctx_per_slot=WINDOW
    )
    assert sorted((u.host, u.port) for u in units) == [("srv2", 8001), ("srv2", 8002)]
