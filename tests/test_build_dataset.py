"""#210: the dataset builder's unit of identity is the (problem, language) arm.

#197 landed the problem pool as **paired arms** — one id names a contract in
both ``tools/problems/tasks/ts`` and ``…/py`` — and this builder was written
when the corpus was twenty TypeScript problems. These tests pin the two
invariants that paired arms make load-bearing:

- the ``--cap`` budget is per arm, so one language cannot consume a problem's
  whole allowance and leave the other with nothing;
- the validation split holds out whole *problems*, so a problem's two arms —
  near-translations of each other — never straddle train and val.

Plus the determinism the tool has always claimed: same inputs, same bytes,
regardless of the order ``golden.json`` happens to list its entries in.

The fixture is synthetic and tiny on purpose. The real corpus is asserted whole
by ``test_reply_corpus.py``; what is under test here is the curation, and a
curation bug is only visible when you control exactly which replies exist.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent


def _builder() -> types.ModuleType:
    """The builder, imported by path — ``tools/`` is not a package."""
    spec = importlib.util.spec_from_file_location(
        "finetune_build_dataset", REPO / "tools" / "finetune" / "build_dataset.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _by_path(name: str, path: Path) -> types.ModuleType:
    """A tool module, imported by path — ``tools/`` is not a package."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


#: The real declaration (#230). The fixtures below run on pool ids and pool
#: tiers, which it declares clean; the guard tests reach for a declared tier
#: on purpose.
INSTRUMENTS = _by_path("instruments", REPO / "tools" / "instruments.py")


class _Language:
    def __init__(self, name: str) -> None:
        self.name = name


class _Task:
    def __init__(self, task_id: str, language: _Language) -> None:
        self.id = task_id
        self.language = language
        # The contract stands in for the real one; all the builder does with it
        # is hand it to build_prompt, and all this stub needs is that the two
        # arms of a problem produce different prompts.
        self.contract = f"{task_id}:{language.name}"


class _Prompt:
    def __init__(self, contract: str) -> None:
        self.system = f"system for {contract}"
        self.user = f"user for {contract}"


#: The tiers the stub can resolve. ``d1`` is here because #240 released the set
#: it names: a retired tier is no longer measurable, but its contracts are still
#: what a prompt behind one of its replies has to be rebuilt from.
_LANGUAGES = {
    "pool-ts": _Language("jsts"),
    "pool-py": _Language("python"),
    "d1": _Language("jsts"),
}


class _FakeBreadth:
    """Stands in for ``tools/breadth/measure.py``.

    The real one resolves a tier to contracts on disk; the builder only asks it
    two things, and both are stubbed to be pure functions of (tier, task).
    """

    @staticmethod
    def load_tier_tasks(tier: str, only: tuple[str, ...] = ()) -> list[_Task]:
        language = _LANGUAGES[tier]
        return [_Task(task_id, language) for task_id in only]

    @staticmethod
    def build_prompt(contract: str) -> _Prompt:
        return _Prompt(contract)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Corpus:
    """A synthetic corpus: reply files on disk, results rows, golden entries."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.entries: list[dict[str, Any]] = []
        self.runs: dict[str, list[dict[str, Any]]] = {}
        self.tiers: dict[str, str] = {}

    def add(
        self,
        *,
        run: str,
        tier: str | None,
        task: str,
        model: str,
        reply: str,
        sample: str = "greedy",
        draw: int = 0,
        passed: bool = True,
    ) -> None:
        if tier is not None:
            self.tiers[run] = tier
        rel = f"candidates/{task}/{sample}-{draw}.txt"
        path = self.root / run / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(reply, encoding="utf-8")
        self.runs.setdefault(run, []).append(
            {"task": task, "arm": sample, "draw": draw, "passed": passed}
        )
        self.entries.append(
            {
                "run": run,
                "file": rel,
                "sha256": _sha(reply),
                "model": model,
                "expect": {"content_sha256": _sha(reply)},
            }
        )

    def write(
        self,
        golden: Path,
        *,
        bundle_sha: str | None = None,
        stamps: dict[str, list[str]] | None = None,
        meta_extra: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Lay the corpus down, stamped the way ``pin.py`` would stamp it.

        The stamp is computed from the real declaration rather than asserted
        here, so a fixture cannot claim a provenance the tool under test would
        disagree with — that disagreement is itself fatal (#230), and a test
        that hard-coded the stamps would be exercising the wrong branch.
        ``stamps`` overrides it, for the tests that need them to disagree;
        ``meta_extra`` adds fields to a run's ``run.json`` — digests, mostly,
        which is how a set with no tier name of its own is recognised.
        """
        verdicts: dict[str, dict[str, Any]] = {}
        for run, rows in self.runs.items():
            run_dir = self.root / run
            meta: dict[str, Any] = {}
            if run in self.tiers:
                meta["tier"] = self.tiers[run]
            meta.update((meta_extra or {}).get(run, {}))
            if bundle_sha is not None:
                meta["bundle_sha256"] = bundle_sha
            (run_dir / "run.json").write_text(json.dumps(meta), encoding="utf-8")
            (run_dir / "results.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
            )
            verdict = INSTRUMENTS.classify(meta, where=run)
            verdicts[run] = {
                "sets": list(verdict.sets),
                "primary": verdict.primary,
                "why": verdict.why,
            }
        if stamps is not None:
            for run, sets in stamps.items():
                verdicts.setdefault(run, {"primary": None, "why": "fixture"})
                verdicts[run]["sets"] = list(sets)
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(
            json.dumps(
                {
                    "entries": self.entries,
                    "instruments": {
                        "declared": "tools/instruments.json",
                        "runs": verdicts,
                    },
                }
            ),
            encoding="utf-8",
        )


@pytest.fixture
def wired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """The builder with its corpus roots pointed at a temp tree."""
    module = _builder()
    monkeypatch.setattr(module, "MEASUREMENTS", tmp_path / "measurements")
    monkeypatch.setattr(
        module, "GOLDEN", tmp_path / "corpus" / "golden.json", raising=False
    )
    monkeypatch.setattr(module, "_load_breadth", lambda: _FakeBreadth)
    return module


def _paired(corpus: Corpus, task: str, *, draws: int, model: str = "m1") -> None:
    """One problem, both arms, ``draws`` distinct replies in each."""
    for tier, run in (("pool-ts", "ts-run"), ("pool-py", "py-run")):
        for draw in range(draws):
            corpus.add(
                run=run,
                tier=tier,
                task=task,
                model=model,
                reply=f"{task} {tier} solution {draw}",
                draw=draw,
            )


def test_the_cap_is_per_arm_not_per_problem(
    wired: types.ModuleType, tmp_path: Path
) -> None:
    """A cap of one keeps one example *per language*, not one per problem.

    This is the #210 defect exactly: keyed on the bare problem id, the two arms
    shared a budget and whichever sorted first took it all.
    """
    corpus = Corpus(tmp_path / "measurements")
    _paired(corpus, "p001-alpha", draws=3)
    corpus.write(wired.GOLDEN)

    manifest = wired.build(1, tmp_path / "out")

    assert manifest["counts"]["problems"] == 1
    assert manifest["counts"]["arms"] == 2
    assert manifest["counts"]["by_language"] == {"jsts": 1, "python": 1}


def test_both_arms_of_a_problem_land_on_the_same_side(
    wired: types.ModuleType, tmp_path: Path
) -> None:
    """No problem straddles train and val under the default split.

    Enough problems to be a real test of the bucket rule rather than a lucky
    draw: with a per-reply split some of these would split across sides.
    """
    corpus = Corpus(tmp_path / "measurements")
    for n in range(30):
        _paired(corpus, f"p{n:03d}-task", draws=2)
    corpus.write(wired.GOLDEN)

    out = tmp_path / "out"
    wired.build(40, out)

    sides: dict[str, set[str]] = {}
    for name in ("train", "val"):
        for line in (out / f"{name}.jsonl").read_text(encoding="utf-8").splitlines():
            system = json.loads(line)["messages"][0]["content"]
            sides.setdefault(system.split()[2].split(":")[0], set()).add(name)

    straddling = {task for task, seen in sides.items() if len(seen) > 1}
    assert straddling == set(), f"problems split across train and val: {straddling}"
    # And the split is not degenerate — something was actually held out.
    assert any("val" in seen for seen in sides.values())


def test_split_by_reply_preserves_the_original_rule(
    wired: types.ModuleType, tmp_path: Path
) -> None:
    """``--split-by reply`` is #189's rule byte for byte, so old sets reproduce."""
    corpus = Corpus(tmp_path / "measurements")
    for n in range(20):
        _paired(corpus, f"p{n:03d}-task", draws=2)
    corpus.write(wired.GOLDEN)

    manifest = wired.build(40, tmp_path / "out", "reply")

    assert manifest["split_by"] == "reply"
    val_shas = {
        e["sha256"] for e in manifest["examples"] if int(e["sha256"], 16) % 10 == 0
    }
    assert manifest["counts"]["val"] == len(val_shas)


def test_output_does_not_depend_on_corpus_entry_order(
    wired: types.ModuleType, tmp_path: Path
) -> None:
    """The same reply captured by two runs must not make the output order-dependent.

    Dedup is first-wins by sha, and the survivor's ``model`` steers the
    round-robin — so without a deterministic tie-break, reversing golden.json's
    entry list could change which examples are kept.
    """
    corpus = Corpus(tmp_path / "measurements")
    _paired(corpus, "p001-alpha", draws=2)
    # The same bytes, captured again by a second run under a different model.
    corpus.add(
        run="ts-run-b",
        tier="pool-ts",
        task="p001-alpha",
        model="m2",
        reply="p001-alpha pool-ts solution 0",
    )
    corpus.write(wired.GOLDEN)

    first = wired.build(40, tmp_path / "out-a")
    corpus.entries.reverse()
    corpus.write(wired.GOLDEN)
    second = wired.build(40, tmp_path / "out-b")

    assert first["examples"] == second["examples"]
    for name in ("train.jsonl", "val.jsonl", "manifest.json"):
        assert (tmp_path / "out-a" / name).read_bytes() == (
            tmp_path / "out-b" / name
        ).read_bytes()


def test_a_failed_reply_is_never_training_material(
    wired: types.ModuleType, tmp_path: Path
) -> None:
    """Only verified passes are emitted — the tool's whole premise."""
    corpus = Corpus(tmp_path / "measurements")
    corpus.add(
        run="ts-run",
        tier="pool-ts",
        task="p001-alpha",
        model="m1",
        reply="wrong",
        passed=False,
    )
    corpus.write(wired.GOLDEN)

    manifest = wired.build(40, tmp_path / "out")

    assert manifest["counts"]["train"] == 0
    assert manifest["counts"]["val"] == 0
    assert manifest["counts"]["dropped"]["not-passed"] == 1


def test_corpus_rot_stops_the_build(wired: types.ModuleType, tmp_path: Path) -> None:
    """A reply whose bytes moved since it was pinned is refused, not used."""
    corpus = Corpus(tmp_path / "measurements")
    _paired(corpus, "p001-alpha", draws=1)
    corpus.write(wired.GOLDEN)
    victim = tmp_path / "measurements" / "ts-run" / "candidates" / "p001-alpha"
    (victim / "greedy-0.txt").write_text("edited after pinning", encoding="utf-8")

    with pytest.raises(SystemExit, match="corpus rot"):
        wired.build(40, tmp_path / "out")


def test_prompt_drift_stops_the_build(wired: types.ModuleType, tmp_path: Path) -> None:
    """A run whose pinned bundle no longer rebuilds is refused.

    A training pair whose prompt is not the prompt the reply answered is worse
    than a missing one.
    """
    corpus = Corpus(tmp_path / "measurements")
    _paired(corpus, "p001-alpha", draws=1)
    corpus.write(wired.GOLDEN, bundle_sha=_sha("a prompt nobody assembles"))

    with pytest.raises(SystemExit, match="prompt drift"):
        wired.build(40, tmp_path / "out")


def test_an_unknown_split_mode_is_refused(
    wired: types.ModuleType, tmp_path: Path
) -> None:
    with pytest.raises(SystemExit, match="unknown --split-by"):
        wired.build(40, tmp_path / "out", "by-vibes")


# --- #230, #240: a training example comes only from a set marked trainable --


def test_a_released_set_is_drawn_from_and_the_manifest_says_so(
    wired: types.ModuleType, tmp_path: Path
) -> None:
    """#240 released the five local sets, and release has to be legible.

    ``d1`` *is* ``tools/bundle/tasks/`` — half the floor instrument — and #189
    drew 622 examples from it while scoring on the same twenty contracts. What
    made that a defect was measuring on it afterwards, and #240 retired it, so
    the material is now drawable. The thing that must not happen is drawing it
    *silently*: a reader has to be able to see that this corpus contains a
    retired ruler's replies.
    """
    corpus = Corpus(tmp_path / "measurements")
    for draw in range(3):
        corpus.add(
            run="d1-run",
            tier="d1",
            task="t01",
            model="m1",
            reply=f"t01 solution {draw}",
            draw=draw,
        )
    corpus.write(wired.GOLDEN)

    manifest = wired.build(40, tmp_path / "out")

    assert manifest["counts"]["train"] + manifest["counts"]["val"] == 3
    released = manifest["instruments"]["released"]
    assert released["replies"] == {"bundle-ts": 3}
    assert released["runs"] == ["d1-run"]
    assert "bundle-ts" in released["sets"]
    assert manifest["instruments"]["refused"]["replies"] == {}
    assert (tmp_path / "out" / "train.jsonl").read_text(encoding="utf-8") != ""


def test_material_that_is_retired_but_not_trainable_is_still_refused(
    wired: types.ModuleType, tmp_path: Path
) -> None:
    """The two flags cannot collapse into one.

    Every declared set is retired, so a guard keyed on retirement would now
    release everything — including HumanEval+, which #240 retired *and* barred
    from training permanently, because its exposure cannot be established and
    a tune that had seen it would make every published comparison unreadable.
    The set is external and has no contracts here, so it is recognised the only
    way it can be: by its id space, vendored beside the pool gate that already
    screens against it.
    """
    corpus = Corpus(tmp_path / "measurements")
    corpus.add(run="he-run", tier="pool-py", task="he12", model="m1", reply="he12 py")
    corpus.add(
        run="clean-run",
        tier="pool-py",
        task="p001-alpha",
        model="m1",
        reply="p001-alpha pool-py solution 0",
    )
    corpus.write(
        wired.GOLDEN,
        meta_extra={"he-run": {"tasks_sha256": {"HumanEval/12": "0" * 64}}},
    )

    manifest = wired.build(40, tmp_path / "out")

    refused = manifest["instruments"]["refused"]
    assert refused["sets"] == ["humaneval-plus"]
    assert refused["replies"] == {"humaneval-plus": 1}
    assert refused["runs"] == ["he-run"]
    assert manifest["counts"]["train"] + manifest["counts"]["val"] == 1


def test_a_corpus_with_no_stamps_is_refused(
    wired: types.ModuleType, tmp_path: Path
) -> None:
    """A pre-#230 corpus cannot say what it holds, so it cannot be drawn from."""
    corpus = Corpus(tmp_path / "measurements")
    corpus.add(
        run="ts-run",
        tier="pool-ts",
        task="p001-alpha",
        model="m1",
        reply="p001-alpha pool-ts solution 0",
    )
    corpus.write(wired.GOLDEN)
    golden = json.loads(wired.GOLDEN.read_text(encoding="utf-8"))
    del golden["instruments"]
    wired.GOLDEN.write_text(json.dumps(golden), encoding="utf-8")

    with pytest.raises(wired.Contamination, match="no instrument stamps"):
        wired.build(40, tmp_path / "out")


def test_a_stamp_that_disagrees_with_the_declaration_is_fatal(
    wired: types.ModuleType, tmp_path: Path
) -> None:
    """Two checks, and disagreement resolves to a stop rather than to the
    permissive answer.

    A set declared *after* the corpus was last pinned is the case that
    matters: the stamp says clean because nothing knew better at pin time,
    and merging the two answers would prefer exactly that stale one.
    """
    corpus = Corpus(tmp_path / "measurements")
    corpus.add(run="d1-run", tier="d1", task="t01", model="m1", reply="t01 sol")
    corpus.write(wired.GOLDEN, stamps={"d1-run": []})

    with pytest.raises(wired.Contamination, match="re-pin"):
        wired.build(40, tmp_path / "out")


def test_an_unstamped_run_is_not_a_clean_run(
    wired: types.ModuleType, tmp_path: Path
) -> None:
    corpus = Corpus(tmp_path / "measurements")
    corpus.add(
        run="ts-run",
        tier="pool-ts",
        task="p001-alpha",
        model="m1",
        reply="p001-alpha pool-ts solution 0",
    )
    corpus.write(wired.GOLDEN)
    golden = json.loads(wired.GOLDEN.read_text(encoding="utf-8"))
    golden["instruments"]["runs"] = {}
    wired.GOLDEN.write_text(json.dumps(golden), encoding="utf-8")

    with pytest.raises(wired.Contamination, match="no instrument stamp"):
        wired.build(40, tmp_path / "out")


def test_a_tierless_run_is_not_silently_treated_as_d1(
    wired: types.ModuleType, tmp_path: Path
) -> None:
    """The default that used to sit here named the instrument.

    ``tier = run_meta.get("tier", "d1")`` meant a run that never said what it
    served had its replies rebuilt against the bundle set's contracts and
    labelled with the instrument's tier. A run that clears the instrument
    check but cannot say what it served is refused instead of guessed at.
    """
    corpus = Corpus(tmp_path / "measurements")
    corpus.add(run="nameless", tier=None, task="p001-alpha", model="m1", reply="x")
    corpus.write(
        wired.GOLDEN,
        meta_extra={"nameless": {"tasks_sha256": {"p001-alpha": "abc123"}}},
    )

    with pytest.raises(wired.Contamination, match="declares no tier"):
        wired.build(40, tmp_path / "out")


def test_the_belt_refuses_what_the_drop_missed(wired: types.ModuleType) -> None:
    """The last check reads the classification, not the drop counters.

    Exercised directly because its whole purpose is to survive a bug in the
    loop above it — a state the loop itself will not produce on demand.
    """
    verdict = INSTRUMENTS.classify({"tasks_sha256": {"HumanEval/3": "0" * 64}})
    kept = [{"run": "he-run", "task": "he03", "language": "python"}]

    with pytest.raises(wired.Contamination, match="humaneval-plus"):
        wired.refuse_withheld_material(kept, {"he-run": verdict}, INSTRUMENTS)

    with pytest.raises(wired.Contamination, match="never classified"):
        wired.refuse_withheld_material(kept, {}, INSTRUMENTS)
