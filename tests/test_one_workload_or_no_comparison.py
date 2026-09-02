"""Every driver in this campaign draws the same prompts, or nothing measured by
one may be compared with anything measured by another.

Matched prompts are necessary and never sufficient. They make two rows *honest* —
same text, same token counts — they do not make a llama.cpp row and a vLLM row
comparable. Those are different stacks (scheduler, batching, KV, quant format)
and no ratio across them attributes anything. What the digest guards is
comparability *within* an engine, across drivers.

The first test is green today and is the control: it recomputes the digest from
the three drivers in the tree. The second is owed — it asks each run artifact to
*name* the driver it ran under, so a reader can recompute rather than trust a
constant pasted into a header.

Over generated prompts, never over source text. The source hash moved under a
``ruff format`` pass in 90635351, and a formatter must not be able to void a
comparison.
"""

from __future__ import annotations

import pytest

from tests.sweeprows import REPO, WORKLOAD_DIGEST, owed, workload_digest

DRIVERS = (
    "vllm_sweep_31-08-2026.py",
    "lcp_sweep_31-08-2026.py",
    "vllm_cores_01-09-2026.py",
)
RUN_FILES = ("srv1-lcpp-arms.tsv", "srv1-moe-slots.tsv", "srv1-vllm-arms.tsv")

#: Guideline 4 files microbenchmarks apart from the serving claim. Both of these
#: hold `llama-bench` numbers — `srv1-llama-bench.tsv` is the instrument record
#: (spread, `-fa 0,1`), `srv1-build-ladder.tsv` re-files one row per rung beside
#: the BUILD and KERNELS stamps that make the ladder readable in one place. Same
#: measurement, so the same rule reaches both: neither may claim the workload.
MICROBENCH = ("srv1-llama-bench.tsv", "srv1-build-ladder.tsv")


@pytest.mark.parametrize("name", DRIVERS)
def test_every_driver_in_the_tree_generates_the_one_workload(name: str) -> None:
    assert workload_digest(REPO / name) == WORKLOAD_DIGEST, (
        f"{name} draws different prompts. Every comparison in this campaign "
        "is void until it does not."
    )


@pytest.mark.parametrize("name", RUN_FILES)
def test_each_artifact_names_the_driver_it_ran_and_that_driver_still_hashes(
    name: str,
) -> None:
    sweep = owed(name)
    stamp = sweep.stamp("WORKLOAD")
    assert stamp.get("digest") == WORKLOAD_DIGEST, (
        f"{name} was measured under workload {stamp.get('digest')!r}, not "
        f"{WORKLOAD_DIGEST!r}. Nothing in it may be compared with anything else."
    )
    driver = REPO / stamp.get("driver", "")
    assert driver.is_file(), (
        f"{name} names driver {stamp.get('driver')!r}, which is not in the tree. "
        "A digest nothing can be recomputed from is a string."
    )
    assert workload_digest(driver) == stamp["digest"], (
        f"{driver.name} no longer generates the workload {name} says it ran under."
    )


@pytest.mark.parametrize("name", MICROBENCH)
def test_microbenchmarks_are_filed_where_no_cross_engine_claim_can_reach_them(
    name: str,
) -> None:
    """``llama-bench`` uses none of the workload — no template, no deciles, no
    scaffold, no sampler. Its numbers are the only honest prefill measurement
    available and they are simultaneously the easiest to misquote as serving
    throughput. Keep them in their own files, stamped as digest-free.

    Both files that carry ``BENCH`` rows are stamped, not just the one named
    after the tool. The build ladder holds the same ``llama-bench`` numbers, and
    a ladder rung quoted as a serving gain is precisely the misreading guideline
    4 exists to block — "the arch spoof is worth 1.7x" was written from exactly
    that kind of number."""
    sweep = owed(name)
    stamp = sweep.stamp("WORKLOAD")
    assert stamp.get("digest") == "none", (
        f"{name} claims a workload digest. It has none: llama-bench generates "
        "synthetic token counts and shares nothing with the serving drivers."
    )
    assert stamp.get("comparable_with") == "microbenchmark-only"
