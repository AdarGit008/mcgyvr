"""#230 — the instrument declaration, and the three consumers that read it.

``tools/instruments.json`` says which task sets the project measures with.
Everything here holds that declaration to being *one* declaration: the pool
gate, the reply pin and the dataset builder must all reach the same answer,
because the failure this issue was filed for is what happens when one producer
respects an instrument and the others have never heard of it.

The load-bearing case is ``d1``. It is not a copy of ``tools/bundle/tasks/``,
it **is** that directory — so a guard keyed on the name a rig happened to use
protects nothing, and #189 drew 622 training examples through exactly that gap.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
GOLDEN = REPO / "records" / "corpora" / "worker-replies" / "golden.json"


def _by_path(name: str, path: Path) -> types.ModuleType:
    """A tool module, imported by path — ``tools/`` is not a package."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


instruments = _by_path("instruments", REPO / "tools" / "instruments.py")
admit = _by_path("pool_admit", REPO / "tools" / "problems" / "admit.py")


# --- the declaration itself ------------------------------------------------


def test_every_declared_set_is_on_disk_with_contracts() -> None:
    """A declaration naming an absent directory would silently protect nothing."""
    for inst in instruments.declared():
        assert inst.root.is_dir(), f"{inst.id}: {inst.root} does not exist"
        assert inst.task_ids, f"{inst.id}: no contracts under {inst.root}"


def test_the_two_bundle_arms_are_declared_as_one_instrument() -> None:
    """Paired ids, mutually declared — the cross-language case, as data.

    Two-thirds of the Python arm is the TypeScript arm restated, and #189
    measured positive transfer between them, so protecting one arm and not the
    other is not protection.
    """
    by_id = {inst.id: inst for inst in instruments.declared()}
    ts, py = by_id["bundle-ts"], by_id["bundle-py"]
    assert "bundle-py" in ts.paired_with
    assert "bundle-ts" in py.paired_with
    assert ts.task_ids == py.task_ids
    assert (ts.language, py.language) == ("jsts", "python")


def test_d1_is_the_bundle_set_rather_than_a_copy_of_it() -> None:
    """The fact that made #189 possible, pinned as an assertion.

    ``load_tier_tasks`` returns ``bundle.load_tasks()`` for ``d1``. If that
    ever becomes a real directory of its own, this fails and the declaration
    needs a new entry rather than a tier alias.
    """
    breadth = _by_path("breadth_measure", REPO / "tools" / "breadth" / "measure.py")
    assert instruments.tier_owner("d1") == "bundle-ts"
    assert not (REPO / "tools" / "breadth" / "tasks" / "d1").exists()
    d1 = {task.id: task for task in breadth.load_tier_tasks("d1")}
    bundle_ts = next(i for i in instruments.declared() if i.id == "bundle-ts")
    assert set(d1) == set(bundle_ts.task_ids)


def test_the_pool_gate_reads_the_same_declaration() -> None:
    """``admit.py`` keeps no second list of roots."""
    assert tuple(admit.existing_task_roots()) == instruments.task_roots()


def test_a_set_added_to_the_declaration_reaches_every_consumer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One declaration, not three that happen to agree today.

    Declaring a set is the whole interface: the pool gate must start refusing
    collisions with it and the classifier must start recognising runs of it,
    without either being edited.
    """
    root = tmp_path / "tasks" / "made-up"
    (root / "z01").mkdir(parents=True)
    (root / "z01" / "contract.yaml").write_text("id: z01\n", encoding="utf-8")
    declaration = tmp_path / "instruments.json"
    declaration.write_text(
        json.dumps(
            {
                "record": "instruments/1",
                "sets": [
                    {
                        "id": "made-up",
                        "root": str(root.relative_to(tmp_path)),
                        "language": "jsts",
                        "tiers": ["z"],
                        "paired_with": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(instruments, "REPO", tmp_path)
    monkeypatch.setattr(instruments, "DECLARATION", declaration)
    instruments.declared.cache_clear()
    try:
        assert [p.name for p in admit.existing_task_roots()] == ["made-up"]
        assert instruments.tier_owner("z") == "made-up"
        assert instruments.classify({"tier": "z"}).sets == ("made-up",)
    finally:
        instruments.declared.cache_clear()


# --- classification --------------------------------------------------------


def test_a_declared_tier_is_recognised() -> None:
    verdict = instruments.classify({"tier": "d1"})
    assert verdict.sets == ("bundle-ts",)
    assert verdict.primary == "bundle-ts"
    assert "tier 'd1'" in verdict.why


def test_an_undeclared_name_over_declared_contracts_is_recognised() -> None:
    """A copy under a new tier name is caught by the contract digests.

    This is the rename case: the same twenty contracts, served as something
    the declaration has never heard of.
    """
    digests = next(i for i in instruments.declared() if i.id == "bundle-ts").digests()
    verdict = instruments.classify(
        {"tier": "totally-new-tier", "tasks_sha256": digests}
    )
    assert verdict.sets == ("bundle-ts",)
    assert "digest" in verdict.why


def test_the_python_arm_is_recognised_without_a_tier_name() -> None:
    """#227 left the Python half with no tier; it is an instrument regardless."""
    digests = next(i for i in instruments.declared() if i.id == "bundle-py").digests()
    verdict = instruments.classify({"tasks_sha256": digests})
    assert verdict.sets == ("bundle-py",)


def test_edited_contracts_under_no_tier_still_fall_in_the_id_space() -> None:
    """The weakest evidence, and the only evidence one real run leaves.

    ``breadth-2026-08-06`` recorded no tier and pinned ``d1`` digests that
    have since been edited, so neither strong rule fires. Its ids are still
    instrument ids, and that is a detection — with an honest refusal to say
    *which* set, since five of them share the shape.
    """
    stale = {f"t{n:02d}": "stale" * 8 for n in range(1, 21)}
    verdict = instruments.classify({"tasks_sha256": stale})
    assert "bundle-ts" in verdict.sets
    assert set(verdict.sets) == {
        "breadth-d1r",
        "breadth-d2",
        "breadth-d3",
        "bundle-py",
        "bundle-ts",
    }
    assert verdict.primary is None
    assert "id space" in verdict.why


def test_pool_material_is_clean() -> None:
    verdict = instruments.classify(
        {"tier": "pool-ts", "tasks_sha256": {"p001-parse-duration": "deadbeef"}}
    )
    assert verdict.sets == ()
    assert not verdict


def test_a_run_that_declares_nothing_cannot_be_cleared() -> None:
    """Silence is not an acquittal — an unclassifiable run raises."""
    with pytest.raises(instruments.InstrumentError, match="cannot be decided"):
        instruments.classify({}, where="mystery-run")


# --- the corpus as it actually stands --------------------------------------


def _golden() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return doc


def test_every_pinned_run_carries_a_verdict() -> None:
    """No entry in the corpus comes from a run nobody classified."""
    golden = _golden()
    runs = golden["instruments"]["runs"]
    for entry in golden["entries"]:
        assert entry["run"] in runs, entry["run"]


def test_the_corpus_agrees_with_the_declaration_today() -> None:
    """Recomputed, not trusted — the stamps are only as good as their date."""
    measurements = REPO / "records" / "measurements"
    golden = _golden()
    for run, stamp in golden["instruments"]["runs"].items():
        manifest = measurements / run / "run.json"
        meta = (
            json.loads(manifest.read_text(encoding="utf-8"))
            if manifest.is_file()
            else {}
        )
        rows = (measurements / run / "results.jsonl").read_text(encoding="utf-8")
        task_ids = {
            json.loads(line)["task"] for line in rows.splitlines() if line.strip()
        }
        live = instruments.classify(meta, where=run, task_ids=task_ids)
        assert list(live.sets) == stamp["sets"], run


def test_the_instrument_reply_count_is_the_stamped_total() -> None:
    golden = _golden()
    runs = golden["instruments"]["runs"]
    counted = sum(1 for e in golden["entries"] if runs[e["run"]]["sets"])
    assert counted == golden["totals"]["instrument_replies"]
    # The floor instrument dominates the corpus; if this ever reads zero the
    # guard has been disconnected rather than satisfied.
    assert counted > 0
