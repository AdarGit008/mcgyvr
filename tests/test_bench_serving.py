"""The bench's serving seam (#225): two tiers, manifest-pinned, bench half only.

The bench is the pool's serving pattern pointed at `tools/bench/`: the
language arm lives in the tier name, run identity (`tier` + `tasks_sha256`)
carries it, and the campaign driver never climbs into either. What is new is
the split — the manifest records each admitted problem's half under the
pre-declared rule, and only `split == "bench"` may ever reach a sweep. The
reserve half is #222's training capacity: never a tier, never served, and
its directories live outside the roots `tools/instruments.json` declares.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _by_path(name: str, path: Path) -> types.ModuleType:
    """A tool module, imported by path — ``tools/`` is not a package."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _by_path("bench_admit", REPO / "tools" / "bench" / "admit.py")
breadth = _by_path("breadth_measure", REPO / "tools" / "breadth" / "measure.py")


def _halves() -> tuple[list[str], list[str]]:
    """Live manifest ids as (bench, reserve), superseded ones excluded."""
    bench: list[str] = []
    reserve: list[str] = []
    for entry in gate.manifest_entries():
        if entry.get("superseded_by"):
            continue
        half = bench if entry.get("split") == "bench" else reserve
        half.append(str(entry["id"]))
    return sorted(bench), sorted(reserve)


def test_bench_tiers_load_the_pinned_bench_half_in_both_arms() -> None:
    """The rig seam: bench-ts and bench-py serve every bench-half problem."""
    bench, _ = _halves()
    assert bench, "an empty manifest would make this test vacuous"
    for tier, language in (("bench-ts", "jsts"), ("bench-py", "python")):
        tasks = breadth.load_tier_tasks(tier, only=bench)
        assert sorted(task.id for task in tasks) == bench
        assert {task.language.name for task in tasks} == {language}
        assert {task.contract.id for task in tasks} == set(bench)


def test_bench_tiers_serve_only_the_bench_half() -> None:
    """Neither an unpinned candidate nor a reserve problem is dispatchable.

    The pool learned the candidate half of this on 2026-08-07 (a probe
    recorded 157 pool-py digests against 149 pool-ts mid-batch); the reserve
    half is the bench's own stake — a reserve problem in a run's identity
    would put training capacity inside the instrument.
    """
    bench, reserve = _halves()
    for tier in breadth.BENCH_TIERS:
        served = {task.id for task in breadth.load_tier_tasks(tier)}
        assert served <= set(bench)
        assert not served & set(reserve)
        root = breadth.BENCH_ROOT / tier.removeprefix("bench-")
        on_disk = {p.name for p in root.iterdir() if p.is_dir()}
        assert served == on_disk & set(bench)


def test_bench_tiers_are_not_campaign_rungs() -> None:
    """The campaign climbs TIERS; the bench is an instrument, not a rung."""
    for tier in breadth.BENCH_TIERS:
        assert tier not in breadth.TIERS
        assert tier not in breadth.VARIANT_TIERS
        assert tier not in breadth.POOL_TIERS


def test_the_tree_the_manifest_and_the_split_rule_agree() -> None:
    """`--verify`'s whole contract, held by the suite.

    Every pinned file matches its digest under the root its split names, no
    problem sits under the other root, no directory exists unpinned, and
    every recorded split agrees with the pre-declared rule.
    """
    assert gate.verify_manifest() == []
