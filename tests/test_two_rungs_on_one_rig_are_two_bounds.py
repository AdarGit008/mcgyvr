"""Rung != rig (owner, 2026-09-05): two rungs co-resident on one machine are
two server processes with two bounds, and the ladder counts them as two.

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

#: The window these tests were written against, stated because nothing supplies
#: one any more. ``mcgyvr.serving.DEFAULT_CONTEXT`` was retired on 2026-09-06:
#: the window is what the run declares, so a test is a run and declares its own.
WINDOW = 4096

CO_RESIDENT = """
version: 1
sources:
  srv2_vllm_3b:
    base_url: "http://srv2:8001"
    api: openai
    engine: vllm
    max_parallel: 4
  srv2_vllm_7b:
    base_url: "http://srv2:8002"
    api: openai
    engine: vllm
    max_parallel: 3
ladder:
  tiers:
    - name: local_3b
      source: srv2_vllm_3b
      model: "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"
      max_parallel: 8
    - name: local_7b
      source: srv2_vllm_7b
      model: "Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"
      max_parallel: 8
"""
HF = "/home/someone/.cache/huggingface"


def test_two_sources_on_one_host_are_two_slot_files() -> None:
    assert _slot_stem("http://srv2:8001", "local_3b") != _slot_stem(
        "http://srv2:8002", "local_7b"
    )


def test_a_slot_held_on_one_rung_does_not_count_on_the_other(tmp_path: Path) -> None:
    capacity = Capacity.of(parse(CO_RESIDENT), root=tmp_path)
    assert capacity.limit("srv2_vllm_3b", rung="local_3b") == 8
    assert capacity.limit("srv2_vllm_7b", rung="local_7b") == 8
    with capacity.hold("srv2_vllm_3b", rung="local_3b"):
        assert capacity.in_flight("srv2_vllm_3b", rung="local_3b") == 1
        assert capacity.in_flight("srv2_vllm_7b", rung="local_7b") == 0


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
        ModelSpec("Qwen/Qwen2.5-Coder-3B-Instruct-AWQ", 3.49, 0.0, 1.95, hf_cache=HF),
        ModelSpec("Qwen/Qwen2.5-Coder-7B-Instruct-AWQ", 7.12, 0.0, 4.93, hf_cache=HF),
    )
    units = units_for(
        parse(CO_RESIDENT), {"srv2": scan}, specs=specs, ctx_per_slot=WINDOW
    )
    assert sorted((u.host, u.port) for u in units) == [("srv2", 8001), ("srv2", 8002)]
