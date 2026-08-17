"""The bench's scorer, and the three ways it was silently wrong (#113).

Scoring through ``Gate.run`` is only an improvement if the workspace it scores
in is the one production would gate. Three defects found on 2026-08-12 each
produced a *plausible* pass rate, which is the dangerous kind:

* the checker's own bytecode cache read as the checker mutating the tree, so
  every Python candidate was rejected by its test runner;
* no ``pyproject.toml`` in the workspace, so ruff applied a rule set far wider
  than the project selects — 75 of 257 reference solutions rejected by a rule
  nobody chose;
* a missing linter is an *environment issue* rather than a finding, so the
  TypeScript arm was scored by three rungs while Python was scored by five and
  ``passed`` said nothing about it.

The first two are pinned here against the reference solutions, which are the
corpus's own answers and the cheapest smoke test available. The third is pinned
against the refusal, because the whole point is that it must not be silent.
"""

from __future__ import annotations

import ast
import importlib.util
import shutil
import sys
import tempfile
import types
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.gate.changeset import ChangeSet
from mcgyvr.gate.runner import Gate
from mcgyvr.sandbox.tempdir import TempDirSandbox

REPO = Path(__file__).resolve().parent.parent


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def score() -> Any:
    return _by_path("bench_score_t", REPO / "tools" / "bench" / "score.py")


@pytest.fixture(scope="module")
def measure() -> types.ModuleType:
    return _by_path("breadth_measure_s", REPO / "tools" / "breadth" / "measure.py")


def _js_toolchain_ready() -> bool:
    """Whether the TypeScript arm can be scored at all on this machine.

    Three capabilities, and none of them is "a package is installed" — which is
    the mistake this predicate made on its first day and CI caught within the
    hour. ``require_tool`` resolves every linter with ``shutil.which``, so a
    toolchain sitting in ``node_modules/.bin`` is one the gate **cannot see**:
    `npm ci` had run, the directory was there, the predicate said ready, and
    eslint read as *not installed*. Present is not reachable, which is the same
    shape one layer down from ADR-0025's "installed is not able to reject".

    So: the tools as the gate resolves them, the *pinned* parser they load (a
    global eslint with no ``typescript-eslint`` is the inert case), and a Node
    that strips types, because acceptance for a ``.ts`` target imports the
    solution and a Node without stripping fails the reference for a reason about
    the runner.
    """
    if shutil.which("eslint") is None or shutil.which("prettier") is None:
        return False
    if not (REPO / "node_modules" / "typescript-eslint").is_dir():
        return False
    spec = importlib.util.spec_from_file_location(
        "bundle_measure_js", REPO / "tools" / "bundle" / "measure.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return bool(module.node_runs_typescript())


requires_js_toolchain = pytest.mark.skipif(
    not _js_toolchain_ready(),
    reason="no pinned JS toolchain on PATH, or this Node does not run TypeScript",
)


def test_ci_installs_the_js_toolchain_so_the_skip_cannot_become_permanent() -> None:
    """The guard below must never be the reason the check stops running.

    ``requires_js_toolchain`` is right to skip on a developer's machine and wrong
    to skip on the runner that is supposed to be guarding the property — a check
    that silently skips everywhere is the same defect as a rung that silently
    passes, one layer out.

    This asserts the **workflow**, not the environment, and that is the whole
    point. An environment assertion gated on ``CI`` fails in the *baseline* job,
    which runs this suite through BUILD-05's clean-checkout bootstrap and is
    meant to have no JS toolchain at all. Reading the declaration instead holds
    the one job that must have it, from any machine, with nothing to install.
    """
    workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    test_job = workflow[workflow.index("\n  test:") :]
    assert "npm ci" in test_job, "the test job must install the pinned toolchain"
    assert "node_modules/.bin" in test_job and "GITHUB_PATH" in test_job, (
        "installing is not enough — `require_tool` resolves linters with "
        "shutil.which, so node_modules/.bin must be exported onto PATH or "
        "eslint and prettier read as not installed (ADR-0025)"
    )


def _score_reference(score: types.ModuleType, task: Any) -> Any:
    with tempfile.TemporaryDirectory() as tmp:
        base = score.stage_dir(task, task.contract.target_content, Path(tmp) / "base")
        with TempDirSandbox(base) as sandbox:
            return score.score(task, task.reference.read_text(), sandbox)


# --- the staged workspace ---------------------------------------------------


def test_the_staged_tree_carries_a_gitignore(
    score: types.ModuleType, measure: types.ModuleType
) -> None:
    """Without it, `python accept.py`'s __pycache__ reads as a tree mutation."""
    task = measure.load_tier_tasks("bench-py", ["b002-option-pairs"])[0]
    with tempfile.TemporaryDirectory() as tmp:
        base = score.stage_dir(task, task.contract.target_content, Path(tmp) / "b")
        assert "__pycache__" in (base / ".gitignore").read_text()


def test_the_staged_tree_carries_the_projects_lint_config(
    score: types.ModuleType, measure: types.ModuleType
) -> None:
    """A workspace with no config makes ruff apply rules the project never chose."""
    import tomllib

    with (REPO / "pyproject.toml").open("rb") as fh:
        selected = tomllib.load(fh)["tool"]["ruff"]["lint"]["select"]

    task = measure.load_tier_tasks("bench-py", ["b002-option-pairs"])[0]
    with tempfile.TemporaryDirectory() as tmp:
        base = score.stage_dir(task, task.contract.target_content, Path(tmp) / "b")
        staged = tomllib.loads((base / "pyproject.toml").read_text())
    assert staged["tool"]["ruff"]["lint"]["select"] == selected


def test_the_reference_is_never_staged(
    score: types.ModuleType, measure: types.ModuleType
) -> None:
    """The answer has no business in a workspace a checker runs in."""
    task = measure.load_tier_tasks("bench-py", ["b002-option-pairs"])[0]
    with tempfile.TemporaryDirectory() as tmp:
        base = score.stage_dir(task, task.contract.target_content, Path(tmp) / "b")
        assert not (base / task.reference.name).exists()


# --- the scorer agrees with the corpus's own answers -----------------------


def test_a_reference_solution_clears_the_full_gate(
    score: types.ModuleType, measure: types.ModuleType
) -> None:
    """The end-to-end smoke test that would have caught defects 1 and 2."""
    task = measure.load_tier_tasks("bench-py", ["b002-option-pairs"])[0]
    verdict: Any = _score_reference(score, task)
    assert verdict.passed, verdict.findings
    assert verdict.rejected_by is None


def test_a_scope_violation_fails_on_the_bench_as_it_would_in_production(
    score: types.ModuleType, measure: types.ModuleType
) -> None:
    """#113's named defect: passing the checker while writing outside scope.

    The candidate is the reference with a second file written beside it, which
    the acceptance command is indifferent to and the contract's scope forbids.
    """
    task = measure.load_tier_tasks("bench-py", ["b002-option-pairs"])[0]
    assert task.contract.scope.allow == ("solution.py",)

    with tempfile.TemporaryDirectory() as tmp:
        base = score.stage_dir(task, task.contract.target_content, Path(tmp) / "b")
        with TempDirSandbox(base) as sandbox:
            sandbox.reset()
            workspace = Path(sandbox.workspace)
            (workspace / task.contract.target).write_text(task.reference.read_text())
            (workspace / "elsewhere.py").write_text("VALUE = 1\n")
            changeset = ChangeSet.detect(workspace, sandbox.base_changeset_ref())
            result = Gate().run(changeset, task.contract.scope, acceptance=None)

    verdict = score.as_verdict(result)
    assert not verdict.passed
    assert verdict.rejected_by == "scope"
    # The acceptance command never ran — the gate stopped at the hard rungs.
    assert verdict.rejected_before_acceptance


# --- the refusal, and the positive control under it -------------------------


def test_the_canary_is_rejected_and_the_reference_is_not(
    score: Any, measure: types.ModuleType
) -> None:
    """The property that matters is "can this rung reject", not "is it installed".

    `eslint` installs cleanly and is inert on TypeScript without a parser: it
    emits severity-1 warnings, the adapter counts severity-2, and the rung
    passes everything while looking healthy. Only a candidate that *must* fail
    can tell the two apart.
    """
    task = measure.load_tier_tasks("bench-py", ["b002-option-pairs"])[0]
    report = score.rung_report([task])
    assert report["python"]["reference_passes"]
    assert report["python"]["canary_rejected"]
    assert "lint" in report["python"]["canary_rejected_by"]


@requires_js_toolchain
def test_every_declared_rung_can_reject_on_both_arms(
    score: Any, measure: types.ModuleType
) -> None:
    """The claim ADR-0025 rests on, measured rather than asserted.

    Until 2026-08-13 the Python arm had the test above and the TypeScript arm
    had nothing, because there was no eslint configuration in the repository to
    run — which is precisely the arm where the rung was inert. The gap was
    closed by hand at a terminal, once. This is that probe, kept.

    Both halves matter and they fail differently. ``CANARY_EXPECTS`` is the
    per-language declaration; a rung missing from ``canary_rejected_by`` runs
    and cannot say no, and the *first* jsts canary was bad spacing alone, which
    tripped prettier and left eslint looking healthy.
    """
    # One problem, both arms — the split rule keeps a problem's two languages
    # together, so this is the smallest paired unit the bench actually uses.
    tasks = measure.load_tier_tasks("bench-ts", ["b002-option-pairs"]) + (
        measure.load_tier_tasks("bench-py", ["b002-option-pairs"])
    )
    report = score.rung_report(tasks)
    assert set(report) == {"jsts", "python"}

    for language, row in sorted(report.items()):
        assert row["reference_passes"], (language, row)
        assert not row["environment_issues"], (language, row)
        inert = set(score.CANARY_EXPECTS[language]) - set(row["canary_rejected_by"])
        assert not inert, f"{language}: declared but unable to reject: {sorted(inert)}"

    # And therefore a paired sweep is not refused. This is the assertion that
    # would have failed on every day before ADR-0025, for the true reason.
    assert score.preflight(tasks) == ()


def test_an_inert_rung_is_reported_even_though_its_tool_runs(
    score: Any, measure: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rung that runs and never rejects must not read as a healthy rung."""
    task = measure.load_tier_tasks("bench-py", ["b002-option-pairs"])[0]
    monkeypatch.setattr(
        score,
        "rung_report",
        lambda tasks, gate=None: {
            "python": {
                "reference_passes": True,
                "reference_rejected_by": None,
                "canary_rejected": False,
                "canary_rejected_by": [],
                "environment_issues": [],
            }
        },
    )
    issues = score.preflight([task])
    assert any("cannot reject" in i for i in issues)


def test_arms_scored_by_different_rungs_are_refused(
    score: Any, measure: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The confound that lands inside every paired ts/py contrast."""
    task = measure.load_tier_tasks("bench-py", ["b002-option-pairs"])[0]
    monkeypatch.setattr(
        score,
        "rung_report",
        lambda tasks, gate=None: {
            "python": {
                "reference_passes": True,
                "reference_rejected_by": None,
                "canary_rejected": True,
                "canary_rejected_by": ["format", "lint"],
                "environment_issues": [],
            },
            "jsts": {
                "reference_passes": True,
                "reference_rejected_by": None,
                "canary_rejected": True,
                "canary_rejected_by": ["format"],
                "environment_issues": [],
            },
        },
    )
    with pytest.raises(score.RungUnavailableError, match="different rungs"):
        score.require_rungs([task])


def test_matching_arms_are_not_refused(
    score: Any, measure: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two arms rejecting by the same rungs is the case that must proceed."""
    task = measure.load_tier_tasks("bench-py", ["b002-option-pairs"])[0]
    row = {
        "reference_passes": True,
        "reference_rejected_by": None,
        "canary_rejected": True,
        "canary_rejected_by": ["format", "lint"],
        "environment_issues": [],
    }
    monkeypatch.setattr(
        score, "rung_report", lambda tasks, gate=None: {"python": row, "jsts": row}
    )
    score.require_rungs([task])  # must not raise


# --- the refusal ------------------------------------------------------------


def test_a_missing_rung_refuses_the_sweep_rather_than_shrinking_the_bar(
    score: types.ModuleType, measure: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A skipped linter must stop a run, not quietly change what it measures."""
    task = measure.load_tier_tasks("bench-py", ["b002-option-pairs"])[0]

    monkeypatch.setattr(
        score,
        "preflight",
        lambda tasks, gate=None: ("jsts: eslint not installed - lint skipped",),
    )
    with pytest.raises(score.RungUnavailableError, match="reduced bar"):
        score.require_rungs([task])


def test_the_refusal_names_every_missing_rung(
    score: types.ModuleType, measure: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = measure.load_tier_tasks("bench-py", ["b002-option-pairs"])[0]
    monkeypatch.setattr(
        score, "preflight", lambda tasks, gate=None: ("a: eslint", "b: prettier")
    )
    with pytest.raises(score.RungUnavailableError) as caught:
        score.require_rungs([task])
    assert "eslint" in str(caught.value)
    assert "prettier" in str(caught.value)


def test_a_clean_preflight_does_not_refuse(
    score: types.ModuleType, measure: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = measure.load_tier_tasks("bench-py", ["b002-option-pairs"])[0]
    monkeypatch.setattr(score, "preflight", lambda tasks, gate=None: ())
    score.require_rungs([task])  # must not raise


# --- the old rate is NOT recoverable, and the row must not pretend ----------


def test_rejected_before_acceptance_states_a_fact_not_an_inference(
    score: types.ModuleType,
) -> None:
    """The gate short-circuits, so a cheap rejection means acceptance never ran.

    The tempting field here is "would the old scorer have passed this?", and it
    is unanswerable: `Gate.run` only runs acceptance `if not findings`, so a
    lint-rejected candidate never executed its own test. Recording the fact
    keeps the row honest; inferring the counterfactual would have manufactured
    a historical comparison out of nothing.
    """
    assert not score.Verdict(True, None, (), ()).rejected_before_acceptance
    assert score.Verdict(False, "lint", (), ()).rejected_before_acceptance
    assert score.Verdict(False, "scope", (), ()).rejected_before_acceptance
    assert not score.Verdict(False, "acceptance", (), ()).rejected_before_acceptance


# --- one bar, one ceiling (#262, ADR-0035) ----------------------------------


def test_the_scored_workspace_and_the_digested_one_are_the_same_workspace(
    score: types.ModuleType, measure: types.ModuleType
) -> None:
    """`stage_bar` calls `stage_config`; it used to restate it.

    That is #262 one level in: a bar digest resolved against a workspace no
    candidate is scored in describes nothing. The copy had already begun to
    drift — `prettier.config.mjs` would have entered the scored workspace and
    not the digested one — so the seam is one function and this holds both
    callers to it.

    Compared as file *contents*, not names. A `pyproject.toml` rendered by two
    code paths could carry the same name and two different rule selections,
    which is the failure this is about wearing a passing test.
    """
    with tempfile.TemporaryDirectory() as tmp:
        scored, digested = Path(tmp) / "scored", Path(tmp) / "digested"
        scored.mkdir()
        digested.mkdir()
        score.stage_config(scored)
        measure.stage_bar(digested)
        for staged in (scored, digested):
            assert (staged / "pyproject.toml").is_file()
        staged_names = {p.name for p in scored.iterdir()}
        assert staged_names == {p.name for p in digested.iterdir()}
        for path in sorted(scored.iterdir()):
            if path.is_symlink():  # node_modules points at the repository's tree
                assert (digested / path.name).is_symlink()
                continue
            assert path.read_bytes() == (digested / path.name).read_bytes(), path.name


def test_the_staged_workspace_declares_both_halves_of_the_bar(
    score: types.ModuleType,
) -> None:
    """Every configuration a rung reads is a file the workspace holds.

    #262 acceptance box 2. The Python arm always had this — `lint_config`
    renders `[tool.ruff]` and `[tool.ruff.format]` from the project's own
    settings — and the JS/TS arm had eslint's half and not prettier's, so one
    arm applied a declared style and the other applied its release's defaults.
    """
    with tempfile.TemporaryDirectory() as tmp:
        staged = score.stage_config(Path(tmp))
        assert "[tool.ruff.lint]" in (staged / "pyproject.toml").read_text()
        assert "[tool.ruff.format]" in (staged / "pyproject.toml").read_text()
        if score.ESLINT_CONFIG.is_file():
            assert (staged / score.ESLINT_CONFIG.name).is_file()
        assert (staged / score.PRETTIER_CONFIG.name).is_file()


def test_the_live_instruments_share_one_acceptance_ceiling() -> None:
    """#262 acceptance box 3, as a property rather than as two matching literals.

    `tools/problems/admit.py` carried its own `30.0` under a comment saying it
    was "the same ceiling as the rigs'", while `tools/bench/score.py` scored at
    `120.0` — admission applied a 4x tighter bar than the instrument it was
    rehearsing and claimed the opposite. Asserting equality of two literals
    would have passed on the day they were equal and said nothing after; this
    asserts that admission *reads* the scorer's, so there is one number.
    """
    source = REPO / "tools" / "problems" / "admit.py"
    admit = _by_path("problems_admit_s", source)
    score_mod = _by_path("bench_score_ceiling", REPO / "tools" / "bench" / "score.py")
    assert admit.TIMEOUT_S == score_mod.ACCEPTANCE_TIMEOUT_S

    # Equal is not enough: two literals are equal on the day they are written
    # and say nothing afterwards, which is precisely the state #262 found. The
    # property is that admission holds no number of its own — asserted against
    # the source, because a value read at import is indistinguishable from a
    # literal once the module object exists.
    assigned = [
        node
        for node in ast.parse(source.read_text(encoding="utf-8")).body
        if isinstance(node, ast.Assign)
        and any(t.id == "TIMEOUT_S" for t in node.targets if isinstance(t, ast.Name))
    ]
    assert len(assigned) == 1
    with pytest.raises(ValueError):
        ast.literal_eval(assigned[0].value)


def test_the_retired_rigs_ceiling_is_left_where_it_describes_its_own_rows() -> None:
    """The third copy is not a disagreement to fix. It is a fact about the past.

    `tools/bundle/measure.py`'s arms were retired by #240 and `record_run`
    refuses every call, so its `30.0` sets no ceiling for anything — it
    describes the 31,062 recorded rows measured under it, 127 of them timeouts
    at exactly that value. Raising it to match the live number would rewrite
    what those rows say they were measured under.
    """
    retired = _by_path("bundle_measure_s", REPO / "tools" / "bundle" / "measure.py")
    score_mod = _by_path("bench_score_retired", REPO / "tools" / "bench" / "score.py")
    assert retired.ACCEPTANCE_TIMEOUT_S == 30.0
    assert retired.ACCEPTANCE_TIMEOUT_S != score_mod.ACCEPTANCE_TIMEOUT_S
