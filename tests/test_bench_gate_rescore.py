"""Hand-built cases for the gate re-scorer, with verdicts derived from rung order.

Issue: `#224 <https://github.com/AdarGit008/mcgyvr/issues/224>`_ A2, hole 1.
The tool under test is ``tools/bench/gate_rescore.py``.

**These expectations are not read off the tool.** Every candidate below is a few
lines written by hand, and its expected verdict is derived from the rung order
``mcgyvr.gate.runner``'s docstring states and ``Gate._run_adapter`` implements:

    scope, secrets  (stop here if either fires)
    structured data
    per adapter, per file: syntax, then structure
    per adapter, batched: lint, then format
    acceptance

with ``rejected_by`` being ``findings[0].check`` (``score.as_verdict``). A test
whose expected value is whatever the tool printed would pass against a tool that
scores every candidate ``lint`` and would be worth nothing; the point of the
re-score is that a *specific* rung rejected, so the specific rung is what is
asserted, and it is asserted against the order rather than against the output.

The cases are named for the property each one holds. Between them they cover the
four verdicts a re-score can reach that the acceptance-only scorer could not
(scope, lint, format, and lint-beats-format), the two verdicts the two scorers
share (clean pass, acceptance failure), and the three rows a re-score must
refuse to grade (dispatch error, parse refusal, a candidate that no longer
parses).
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.contract import Contract, loads
from mcgyvr.scope import Scope

REPO = Path(__file__).resolve().parent.parent


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# `tools/` is not a package, so the rig is loaded by path — the convention every
# other `tests/test_bench_*.py` follows.
gate_rescore = _by_path(
    "bench_gate_rescore_t", REPO / "tools" / "bench" / "gate_rescore.py"
)
bundle = _by_path("bundle_measure_t", REPO / "tools" / "bundle" / "measure.py")


# --- the fixture task ------------------------------------------------------
#
# One contract, one acceptance script, one scaffold. Small enough that every
# expected verdict below can be read off the candidate by eye, which is the
# whole point: a fixture that needed explaining could not anchor a hand-derived
# expectation.

CONTRACT_YAML = """\
id: fx01-double
task_type: function_implementation
task: >-
  Implement double. Given an integer, return twice its value.
target: solution.py
target_content: |
  def double(n: int) -> int:
      raise NotImplementedError
interface: "def double(n: int) -> int"
stop_conditions:
  - Whether a non-integer argument should be coerced or refused is not stated.
acceptance: ["python accept.py"]
risk: low
scope:
  allow: ["solution.py"]
"""

ACCEPT_PY = """\
from solution import double

assert double(2) == 4
assert double(0) == 0
assert double(-3) == -6
"""

REFERENCE_PY = """\
def double(n: int) -> int:
    return n * 2
"""


def fenced(body: str) -> str:
    """A worker reply carrying one fenced block, which is the protocol.

    `parse_reply` writes only the contents of a single fence, so a candidate
    file on disk is the *reply*, not the code. Building the reply here rather
    than in each case keeps the cases about the code.
    """
    return f"Here is the implementation.\n\n```python\n{body}```\n"


# --- the candidates, and why each one exists -------------------------------

# Correct, import-free, and already in ruff's own format: nothing for any rung
# to say. The baseline the other cases are read against — without it a suite
# where every candidate is rejected would look identical to a healthy one.
CLEAN = "def double(n: int) -> int:\n    return n * 2\n"

# Correct and well-formatted, but imports a module it never uses. `F401` is in
# the project's select list (`E, F, W, I, N, UP, B, SIM, RUF`), and the blank
# lines are exactly what ruff format emits, so `format` has nothing to add.
# This is the cell the acceptance-only scorer called a pass: the code runs.
LINT_ONLY = "import os\n\n\ndef double(n: int) -> int:\n    return n * 2\n"

# Correct and lint-clean, but single-quoted where the project's format config
# says double. No selected lint rule governs quote style (`Q` is not in the
# select list), so this can only be caught by `format` — which is what makes it
# a clean separation from the case above.
FORMAT_ONLY = "def double(n: int) -> int:\n    'Twice n.'\n    return n * 2\n"

# Both defects at once. The expected verdict is `lint`, and not because lint is
# more serious — `_run_adapter` iterates `(("lint", ...), ("format", ...))` in
# that order and appends to one list, so lint's finding is `findings[0]`. This
# is the one case here that tests an *ordering* rather than a rung, which is why
# it is worth its own name.
LINT_AND_FORMAT = (
    "import os\n\n\ndef double(n: int) -> int:\n    'Twice n.'\n    return n * 2\n"
)

# Runs, lints and formats cleanly, and is wrong. The rungs the gate added cannot
# see it; only the contract's own suite can. This is the case where the strict
# and lenient scorers agree, and it has to be present or "the gate rejects more"
# would be untestable against "the gate rejects everything".
WRONG_ANSWER = "def double(n: int) -> int:\n    return n + 2\n"


def write_task(root: Path) -> Any:
    """The fixture task on disk, its contract through the real loader.

    Loaded rather than hand-constructed so the fixture is a contract this
    project would actually accept — a fixture the loader would reject proves
    nothing about runs made of contracts it accepted.
    """
    directory = root / "fx01-double"
    directory.mkdir(parents=True)
    (directory / "contract.yaml").write_text(CONTRACT_YAML, encoding="utf-8")
    (directory / "accept.py").write_text(ACCEPT_PY, encoding="utf-8")
    (directory / "reference.py").write_text(REFERENCE_PY, encoding="utf-8")
    return bundle.Task(
        id="fx01-double",
        contract=loads(CONTRACT_YAML),
        directory=directory,
        language=bundle.PYTHON,
    )


def write_run(
    root: Path,
    rows: list[dict[str, Any]],
    candidates: dict[tuple[str, int], str],
    *,
    condition: str = "stock",
) -> Path:
    """A measurement directory shaped exactly as the rigs write one."""
    measured = root / "run"
    (measured / "candidates" / "fx01-double").mkdir(parents=True)
    (measured / "run.json").write_text(
        json.dumps(
            {
                "model": "fixture",
                "tier": "bench-py",
                "condition": condition,
                "draws": 1,
            }
        ),
        encoding="utf-8",
    )
    (measured / "results.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    for (arm, draw), text in candidates.items():
        (measured / "candidates" / "fx01-double" / f"{arm}-{draw}.txt").write_text(
            text, encoding="utf-8"
        )
    return measured


def row_for(arm: str, draw: int, *, passed: bool, **extra: Any) -> dict[str, Any]:
    """One acceptance-scored row, as the pre-#113 rigs wrote them.

    Note what is absent: `rejected_by`. Its absence is the defect #224 A2 exists
    to repair, so the fixture must not accidentally supply it.
    """
    return {
        "task": "fx01-double",
        "type": "function_implementation",
        "model": "fixture",
        "arm": arm,
        "draw": draw,
        "temperature": 0.0 if arm == "greedy" else 0.7,
        "stop_reason": "complete",
        "passed": passed,
        "parse_error": None,
    } | extra


#: What the `rescore` fixture hands a case: rescored rows keyed by (arm, draw).
Rescored = dict[tuple[str, int], dict[str, Any]]
Rescorer = Callable[..., Rescored]


@pytest.fixture(autouse=True)
def _pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the round pin for every case in this file, as the breadth rig does.

    ``rescore_dir`` calls ``require_pinned`` against the **real** repository,
    which refuses whenever the tree has moved off the open round — the normal
    state between campaigns, and the unavoidable state while the batch for the
    next boundary is landing (#291). Without this, twelve cases fail for a
    reason none of them is about, and pass only on the days someone happens to
    have opened a round against this exact tree.

    Autouse rather than a parameter each case opts into: the default for a case
    added later must be "pinned", not "coupled to whether a campaign is open".
    That the pin refuses a moved tree is `tests/test_bench_rounds.py`'s
    assertion and is made there.
    """
    monkeypatch.setattr(
        gate_rescore.revision, "require_pinned", lambda *a, **k: ("r-test", "0" * 64)
    )


@pytest.fixture
def rescore(tmp_path: Path) -> Rescorer:
    """Re-score a one-task run built from the given candidates.

    Returns the rescored rows keyed by (arm, draw), so a case reads as "this
    text, that verdict" with no plumbing in between.
    """

    def run(
        candidates: dict[tuple[str, int], str],
        rows: list[dict[str, Any]] | None = None,
        *,
        task: Any = None,
        condition: str = "stock",
        write: bool = True,
    ) -> Rescored:
        fixture_task = task if task is not None else write_task(tmp_path / "tasks")
        built = rows or [row_for(arm, draw, passed=True) for (arm, draw) in candidates]
        measured = write_run(tmp_path, built, candidates, condition=condition)
        gate_rescore.rescore_dir(
            measured, write=write, tasks=[fixture_task], check_toolchain=False
        )
        out: Rescored = {}
        for line in (measured / gate_rescore.ROWS_NAME).read_text().splitlines():
            row = json.loads(line)
            out[(row["arm"], row["draw"])] = row
        return out

    return run


# --- the cases -------------------------------------------------------------


def test_clean_candidate_clears_every_rung(rescore: Rescorer) -> None:
    """No rung has anything to say, so the verdict is a pass and names no rung.

    Exists because every other case asserts a rejection. Without a candidate
    that passes, a tool that rejected unconditionally would satisfy all of them.
    """
    rows = rescore({("greedy", 0): fenced(CLEAN)})
    row = rows[("greedy", 0)]
    assert row["rescored"] is True
    assert row["passed"] is True
    assert row["rejected_by"] is None
    assert row["flipped"] is False


def test_lint_only_candidate_is_rejected_at_lint(rescore: Rescorer) -> None:
    """An unused import: `F401` is selected, and the layout is ruff's own.

    Derived, not observed — the candidate is well-formed for every rung before
    `lint`, so `lint` is the first that can produce a finding.
    """
    rows = rescore({("greedy", 0): fenced(LINT_ONLY)})
    row = rows[("greedy", 0)]
    assert row["passed"] is False
    assert row["rejected_by"] == "lint"
    # It ran on the day and it runs now; only the bar moved. This is the shape
    # of the whole finding #224 A2 is after.
    assert row["passed_before"] is True
    assert row["flipped"] is True
    assert row["rejected_before_acceptance"] is True


def test_format_only_candidate_is_rejected_at_format(rescore: Rescorer) -> None:
    """Single quotes where the config says double, and no lint rule covers it.

    `Q` is not in the project's select list, so this candidate is invisible to
    every rung except `format`. That is what makes it a control on the case
    above rather than a second copy of it.
    """
    rows = rescore({("greedy", 0): fenced(FORMAT_ONLY)})
    row = rows[("greedy", 0)]
    assert row["passed"] is False
    assert row["rejected_by"] == "format"
    assert row["rejected_before_acceptance"] is True


def test_lint_beats_format_when_a_candidate_trips_both(rescore: Rescorer) -> None:
    """Both rungs fire; `rejected_by` is `lint` because `_run_adapter` runs it first.

    The only case here that pins an *order* rather than a rung. It matters
    because every rate this project reads by cause is a tally of `findings[0]`:
    if the two rungs swapped, a column would move with no rate changing, and
    nothing else in the suite would notice.
    """
    rows = rescore({("greedy", 0): fenced(LINT_AND_FORMAT)})
    row = rows[("greedy", 0)]
    assert row["passed"] is False
    assert row["rejected_by"] == "lint"
    # Both defects really are present — otherwise this would silently degrade
    # into a duplicate of the lint-only case and still pass.
    assert "format:" in row["fail_output"]


def test_wrong_answer_is_still_rejected_at_acceptance(rescore: Rescorer) -> None:
    """The rungs the gate added cannot see a wrong answer; the suite can.

    The case where strict and lenient agree. Its verdict must be `acceptance`
    and its `flipped` must be false, or "the gate is stricter" would be
    indistinguishable from "the gate rejects everything".
    """
    rows = rescore(
        {("greedy", 0): fenced(WRONG_ANSWER)},
        rows=[row_for("greedy", 0, passed=False)],
    )
    row = rows[("greedy", 0)]
    assert row["passed"] is False
    assert row["rejected_by"] == "acceptance"
    assert row["rejected_before_acceptance"] is False
    assert row["flipped"] is False


def test_scope_violation_rejects_what_acceptance_would_have_passed(
    tmp_path: Path,
) -> None:
    """The lenient/strict split at its sharpest: correct code, rejected first.

    The candidate is `CLEAN` — it passes the contract's suite. The contract's
    scope does not permit the target, so `scope` fires and the run stops there:
    `Gate.run` returns before structured data, before the adapters and before
    acceptance, so the suite never executes and no row can say what it would
    have done.

    **The contract is built by hand rather than loaded**, and that is itself the
    finding rather than a shortcut. `mcgyvr.contract` refuses a contract whose
    target is outside its own `scope.allow` ("target: ... is outside
    scope.allow"), and the bench writes exactly one file — the target. So across
    every committed gate-scored run the `scope` rung has rejected nothing, and
    it cannot. This case pins the rung's *position*, so that a future contract
    shape which can reach it is scored in the order the gate documents.
    """
    directory = tmp_path / "tasks" / "fx01-double"
    directory.mkdir(parents=True)
    (directory / "accept.py").write_text(ACCEPT_PY, encoding="utf-8")
    (directory / "reference.py").write_text(REFERENCE_PY, encoding="utf-8")
    task = bundle.Task(
        id="fx01-double",
        contract=Contract(
            id="fx01-double",
            task_type="function_implementation",
            task="Implement double.",
            target="solution.py",
            scope=Scope.of(["docs/**"], []),
            target_content=(
                "def double(n: int) -> int:\n    raise NotImplementedError\n"
            ),
            acceptance=("python accept.py",),
        ),
        directory=directory,
        language=bundle.PYTHON,
    )
    measured = write_run(
        tmp_path,
        [row_for("greedy", 0, passed=True)],
        {("greedy", 0): fenced(CLEAN)},
    )
    gate_rescore.rescore_dir(measured, write=True, tasks=[task], check_toolchain=False)
    row = json.loads((measured / gate_rescore.ROWS_NAME).read_text().splitlines()[0])
    assert row["passed"] is False
    assert row["rejected_by"] == "scope"
    assert row["rejected_before_acceptance"] is True
    # Passed under acceptance-only, rejected under the gate. That is the entire
    # gap A2 measures, in one row.
    assert row["passed_before"] is True
    assert row["flipped"] is True


def test_unparseable_reply_is_refused_rather_than_graded(rescore: Rescorer) -> None:
    """A reply with no fenced block has no file in it, so there is nothing to score.

    The row said it parsed on the day. If it does not parse now the parser moved
    under us, and recording a rejection here would attribute to a rung something
    no rung produced. `regrade.py` establishes this rule and it is kept.
    """
    rows = rescore({("greedy", 0): "I cannot help with this request.\n"})
    row = rows[("greedy", 0)]
    assert row["rescored"] is False
    assert row["rescore_skipped"] == "no longer parses: no-fenced-block"
    assert "rejected_by" not in row


def test_a_row_that_never_reached_a_checker_is_carried_forward(
    rescore: Rescorer,
) -> None:
    """A dispatch error is a draw nobody saw; a parse refusal predates every rung.

    No scorer change can move either, so both are copied through and marked.
    Re-scoring them would invent an observation — the candidate does not exist
    in the first case, and in the second the checker never ran.
    """
    rows = rescore(
        {("greedy", 0): fenced(CLEAN)},
        rows=[
            row_for("greedy", 0, passed=False, dispatch_error="RunnerError: timeout"),
            row_for("sampled", 0, passed=False, parse_error="no-fenced-block"),
        ],
    )
    assert rows[("greedy", 0)]["rescored"] is False
    assert rows[("greedy", 0)]["rescore_skipped"] == "dispatch_error"
    assert rows[("sampled", 0)]["rescored"] is False
    assert rows[("sampled", 0)]["rescore_skipped"] == "parse_error"


def test_the_original_results_file_is_never_rewritten(tmp_path: Path) -> None:
    """A record that changes when the tooling changes is not a record.

    `results.jsonl` states what was measured on the day under the scorer of the
    day. The re-score lands beside it under its own name, so a reader who finds
    both can always tell which bar produced which.
    """
    task = write_task(tmp_path / "tasks")
    measured = write_run(
        tmp_path,
        [row_for("greedy", 0, passed=True)],
        {("greedy", 0): fenced(LINT_ONLY)},
    )
    before = (measured / "results.jsonl").read_bytes()
    gate_rescore.rescore_dir(measured, write=True, tasks=[task], check_toolchain=False)
    assert (measured / "results.jsonl").read_bytes() == before
    assert (measured / gate_rescore.ROWS_NAME).is_file()
    assert (measured / gate_rescore.SUMMARY_NAME).is_file()


def test_check_mode_scores_and_writes_nothing(tmp_path: Path) -> None:
    """`--check` must be safe to run against a committed record."""
    task = write_task(tmp_path / "tasks")
    measured = write_run(
        tmp_path,
        [row_for("greedy", 0, passed=True)],
        {("greedy", 0): fenced(LINT_ONLY)},
    )
    summary = gate_rescore.rescore_dir(
        measured, write=False, tasks=[task], check_toolchain=False
    )
    assert summary["rescored"] == 1
    assert not (measured / gate_rescore.ROWS_NAME).exists()
    assert not (measured / gate_rescore.SUMMARY_NAME).exists()


def test_noscaffold_is_diffed_against_the_tree_the_worker_was_shown(
    tmp_path: Path,
) -> None:
    """Under `noscaffold` the base is empty, because that is what the worker saw.

    `Gate.run`'s scope rung judges a *diff*. If the base carried the scaffold the
    worker was told did not exist, the scaffold's disappearance would be
    attributed to the worker. Acceptance-only scoring never looked at a diff,
    which is why `regrade.py` can ignore the condition and this tool cannot —
    getting it wrong would reject every ablated cell and read as a finding.
    """
    task = write_task(tmp_path / "tasks")
    measured = write_run(
        tmp_path,
        [row_for("greedy", 0, passed=True)],
        {("greedy", 0): fenced(CLEAN)},
        condition="noscaffold",
    )
    summary = gate_rescore.rescore_dir(
        measured, write=True, tasks=[task], check_toolchain=False
    )
    assert summary["condition"] == "noscaffold"
    row = json.loads((measured / gate_rescore.ROWS_NAME).read_text().splitlines()[0])
    assert row["passed"] is True
    assert row["rejected_by"] is None


def test_the_summary_states_the_bar_and_the_material_it_was_run_over(
    tmp_path: Path,
) -> None:
    """A re-scored rate is evidence only if it names what produced it.

    The five rungs, the mode, the round and product pin (#231 checks 3 and 6),
    the acceptance-script digests, and a digest of the input run. Someone
    holding this file must be able to re-run the tool and see either the same
    rows or exactly what moved.
    """
    task = write_task(tmp_path / "tasks")
    measured = write_run(
        tmp_path,
        [row_for("greedy", 0, passed=True)],
        {("greedy", 0): fenced(CLEAN)},
    )
    summary = gate_rescore.rescore_dir(
        measured, write=False, tasks=[task], check_toolchain=False
    )
    assert summary["gate_rungs"] == list(
        ("scope", "secrets", "structured", "adapters", "acceptance")
    )
    assert summary["gate_semantic"] is False
    assert summary["scorer_before"].startswith("acceptance command only")
    assert summary["mode"] == "single-tier"
    assert summary["round"] and len(summary["product_sha256"]) == 64
    # The input, pinned by content rather than by directory name — a directory
    # is mutable and could be re-dispatched under the same name.
    assert len(summary["source_sha256"]["results.jsonl"]) == 64
    assert len(summary["source_sha256"]["candidates"]) == 64


def test_a_missing_rung_tool_is_refused_before_the_first_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A degraded run must never be mistaken for a full one.

    The gate records a missing tool as an *environment issue* and still reaches
    a verdict — right for a minimal production box, wrong for an instrument. A
    re-score with ruff absent would be a three-rung bar wearing a five-rung
    label, and would read as evidence that the gate is kinder than it is.
    """
    monkeypatch.setattr(
        gate_rescore.shutil, "which", lambda tool: None if tool == "ruff" else "/x"
    )
    with pytest.raises(gate_rescore.RescoreError, match="ruff"):
        gate_rescore.require_toolchain()
