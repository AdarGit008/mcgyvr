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


_LANGUAGES = {"pool-ts": _Language("jsts"), "pool-py": _Language("python")}


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
        tier: str,
        task: str,
        model: str,
        reply: str,
        sample: str = "greedy",
        draw: int = 0,
        passed: bool = True,
    ) -> None:
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

    def write(self, golden: Path, *, bundle_sha: str | None = None) -> None:
        for run, rows in self.runs.items():
            run_dir = self.root / run
            meta: dict[str, Any] = {"tier": self.tiers[run]}
            if bundle_sha is not None:
                meta["bundle_sha256"] = bundle_sha
            (run_dir / "run.json").write_text(json.dumps(meta), encoding="utf-8")
            (run_dir / "results.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
            )
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(json.dumps({"entries": self.entries}), encoding="utf-8")


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
