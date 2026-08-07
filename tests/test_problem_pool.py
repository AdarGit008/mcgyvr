"""Offline invariants over the problem pool (#197).

Admission itself executes checkers and needs `node` and `python` in the shape
the contracts declare; none of that belongs in the suite, the same way the
rigs' `--selftest` is a stated precondition rather than a test. What the
suite holds the repository to is everything checkable without running a
candidate:

* **The tree is the manifest.** Every pool task on disk is pinned byte for
  byte in ``admissions.jsonl``, and every pin either matches the tree or
  names its successor. Run directories pin the task set's digests, so an
  unpinned edit is not a tidy-up — it refuses prior runs a resume.
* **The id is the join key.** Directory name, contract id in both arms, and
  the ``p<nnn>-<slug>`` shape all agree, and no pool id collides with any
  other task set's — `tools/finetune/build_dataset.py` keys on the bare id.
* **The front door stays held out.** No pool problem implements a symbol
  whose normalised name is a HumanEval entry point, in either arm's casing.
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


admit = _by_path("pool_admit", REPO / "tools" / "problems" / "admit.py")
breadth = _by_path("breadth_measure", REPO / "tools" / "breadth" / "measure.py")


def _pool_ids() -> list[str]:
    ids: set[str] = set()
    for arm in admit.ARMS:
        if arm.root.is_dir():
            ids.update(p.name for p in arm.root.iterdir() if p.is_dir())
    return sorted(ids)


def test_manifest_and_tree_agree() -> None:
    assert admit.verify_manifest() == []


def test_ids_are_shaped_and_agree_across_arms() -> None:
    for problem in _pool_ids():
        assert admit.ID_RE.match(problem), problem
        for arm in admit.ARMS:
            contract = admit.load(arm.root / problem / "contract.yaml")
            assert contract.id == problem
            assert contract.task_type in admit.V1_TYPES


def test_pool_ids_collide_with_no_other_task_set() -> None:
    existing = admit.existing_tasks()
    pool = set(_pool_ids())
    for label, contract in existing.items():
        assert contract.id not in pool, f"{label} shares id {contract.id}"
        assert label.rsplit("/", 1)[-1] not in pool, label


def test_no_pool_symbol_is_a_humaneval_entry_point() -> None:
    blocklist = admit.humaneval_entry_points()
    for problem in _pool_ids():
        for arm in admit.ARMS:
            contract = admit.load(arm.root / problem / "contract.yaml")
            match = arm.interface_re.search(contract.interface)
            if match is not None:
                name = admit._normalise_symbol(match.group(1))
                assert name not in blocklist, f"{problem}: {match.group(1)}"


def test_checkers_meet_the_assertion_floor() -> None:
    for problem in _pool_ids():
        for arm in admit.ARMS:
            text = (arm.root / problem / arm.accept).read_text(encoding="utf-8")
            assert text.count("assert") >= admit.MIN_ASSERTIONS, (
                f"{problem} [{arm.name}]"
            )


def test_pool_tiers_load_pinned_problems_in_both_arms() -> None:
    """The rig seam: pool-ts and pool-py serve every pinned problem.

    Restricted to manifest-pinned ids so a half-written candidate a
    generator is still working on cannot fail the suite — the pinned set
    is the pool; the rest is not yet anything.
    """
    pinned = sorted(
        str(entry["id"])
        for entry in admit.manifest_entries()
        if not entry.get("superseded_by")
    )
    assert pinned, "an empty manifest would make this test vacuous"
    for tier, language in (("pool-ts", "jsts"), ("pool-py", "python")):
        tasks = breadth.load_tier_tasks(tier, only=pinned)
        assert sorted(task.id for task in tasks) == pinned
        assert {task.language.name for task in tasks} == {language}
        assert {task.contract.id for task in tasks} == set(pinned)


def test_pool_tiers_are_not_campaign_rungs() -> None:
    """The campaign climbs TIERS; the pool must not be a rung it can reach."""
    for tier in breadth.POOL_TIERS:
        assert tier not in breadth.TIERS
        assert tier not in breadth.VARIANT_TIERS


def test_pool_prose_stays_below_the_near_duplicate_line() -> None:
    specs = {
        problem: admit._words(
            admit.load(admit.ARMS[0].root / problem / "contract.yaml").task
        )
        for problem in _pool_ids()
    }
    names = sorted(specs)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            score = admit.jaccard(specs[a], specs[b])
            assert score < admit.JACCARD_REJECT, f"{a} vs {b}: {score:.2f}"
