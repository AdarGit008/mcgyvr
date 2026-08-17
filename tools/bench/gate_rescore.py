#!/usr/bin/env python
"""#224 A2 hole 1 — re-score saved candidates under ``Gate.run``, at zero token cost.

**The hole this closes.** Every multi-draw run this project owns — the only
source of ``psi_draw`` — was scored by running the contract's acceptance command
and nothing else, because it predates #113. Its rows carry no ``rejected_by``.
``headroom`` and ``psi``, meanwhile, are gate-scored. So #224's table compares a
lenient-scorer number against a strict-scorer number and cannot say how much of
the gap is the bar rather than the observable. The candidate texts are on disk;
the bar is a pure function of them; the difference is recoverable offline.

**Why this is not** ``tools/bench/regrade.py``. That tool re-runs *acceptance
only*, by design, and its docstring says so — it exists to recover figures after
a **checker** was corrected (ADR-0023's ``ValueError`` asymmetry). Holding the
scorer fixed at acceptance is the property that makes its output comparable with
the runs it re-scores. This tool does the opposite: it holds the candidate fixed
and **changes the scorer**, from acceptance-only to the five rungs the product
ships. Two opposite invariants cannot live behind one flag, so they are two
tools. What is shared is composed rather than copied — ``checker_digests`` is
imported from ``regrade`` and the doctrine below is inherited whole.

**The doctrine, kept from** ``regrade.py``:

* The original ``results.jsonl`` is **never rewritten.** It records what was
  measured on the day under the scorer of the day, and a record that changes
  when the tooling changes is not a record. The re-score lands beside it.
* Rows that never reached a checker are **carried forward and marked**, not
  re-graded. A dispatch error is a draw nobody saw and a parse refusal happened
  before any checker ran; scoring either would invent an observation.
* The candidate text is **re-parsed rather than trusted**, so a row that used to
  parse and now does not is surfaced instead of silently re-graded.

**Why** ``score.score`` **is called rather than reimplemented.** It is the exact
function the live sweep runs (``tools/breadth/measure.py:631``), including the
staged ``pyproject.toml``, the ``.gitignore`` that keeps ``__pycache__`` out of
the changeset, and the linked ``node_modules``. A re-score that scored
differently from a sweep would answer nothing — the whole point is to put
``psi_draw`` on the same bar as ``headroom``, and "the same bar" has to mean the
same code.

**Why the condition matters here and not in** ``regrade``. The scaffold ablations
are re-scored too, and under ``noscaffold`` the worker was told the target file
was empty. ``Gate.run``'s scope rung judges a *diff*, so the tree it is diffed
against must be the tree the worker was shown, or the scaffold's removal is
attributed to the worker and every ablated cell is rejected at ``scope``. The
base is therefore staged from ``breadth.ablate(contract, condition)``, exactly as
the sweep stages it. Acceptance-only scoring never looked at a diff, which is
why ``regrade`` can ignore this and this tool cannot.

**A degraded run is refused, not annotated.** The lint and format rungs shell out
to ``ruff``, ``eslint`` and ``prettier``. A missing tool is an *environment
issue* — the gate records it and does not reject the worker for it — so a
re-score with ruff absent would silently be a three-rung bar wearing a five-rung
label, and would read as "the gate was kinder than we thought". ``score.preflight``
is run first and answers the question that matters, which is not *installed* but
*able to reject*.

Usage::

    uv run --no-sync python tools/bench/gate_rescore.py <dir> [<dir> ...]
    uv run --no-sync python tools/bench/gate_rescore.py --check <dir>

``<dir>`` is a measurement directory holding ``run.json``, ``results.jsonl`` and
``candidates/`` — the same unit ``regrade.py`` takes.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import time
import types
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcgyvr.runner import StopReason
from mcgyvr.sandbox.tempdir import TempDirSandbox
from mcgyvr.worker.reply import ReplyError, parse_reply

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def _by_path(name: str, path: Path) -> types.ModuleType:
    """A tool module, imported by path — ``tools/`` is not a package."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


breadth = _by_path("breadth_measure_gr", REPO / "tools" / "breadth" / "measure.py")
score = _by_path("bench_score_gr", HERE / "score.py")

# Composed, not copied. `checker_digests` is the acceptance-script pin, and it is
# as true of a gate re-score as of an acceptance re-score — the acceptance rung
# is the last thing `Gate.run` runs. A second implementation would be a second
# thing to correct.
regrade = _by_path("bench_regrade_gr", HERE / "regrade.py")

# #231 checks 3 and 6: a figure states the mode it was measured in and the
# product revision that produced it. Imported the way `eligibility.py` and
# `resolution.py` import them, under the same two names.
mode = _by_path("bench_mode_gr", HERE / "mode.py")
revision = _by_path("bench_product_gr", HERE / "product.py")

#: Rows carrying either of these never reached a checker, so no scorer change can
#: move them. Same set and same reason as ``regrade.UNSCORED``, taken from it so
#: the two tools cannot disagree about what "unscored" means.
UNSCORED = regrade.UNSCORED

#: What the re-scored file is called, beside the ``results.jsonl`` it never
#: touches. Deliberately not ``regrade.jsonl`` — a reader who finds both in one
#: directory must be able to tell an acceptance re-run from a scorer change.
ROWS_NAME = "gate-rescore.jsonl"
SUMMARY_NAME = "gate-rescore.json"

#: The external programs the declared rungs shell out to. Presence is necessary
#: and not sufficient — see ``preflight`` below, which asks whether they reject.
TOOLS = ("python", "ruff", "eslint", "prettier", "node")


class RescoreError(Exception):
    """This re-score would not measure what it claims to."""


def missing_tools() -> list[str]:
    """Declared-rung programs that are not on PATH.

    ``python`` is in the list because the contracts declare ``python accept.py``
    and the acceptance rung runs the command a contract declares — not
    :data:`sys.executable`. On this project's machines both it and ``ruff`` live
    in ``.venv/bin``, so a bare invocation finds neither; that is what ``uv run``
    is for, and the refusal below names it.
    """
    return [tool for tool in TOOLS if shutil.which(tool) is None]


def require_toolchain() -> None:
    """Refuse before the first candidate if a rung's program is absent.

    Loud and early rather than per-row: the gate treats a missing tool as an
    environment issue and keeps going to a verdict, which is right for a
    production run on a minimal box and wrong for an instrument. Five thousand
    rows silently scored by three rungs would read as evidence that the bar is
    gentler than it is.
    """
    absent = missing_tools()
    if absent:
        raise RescoreError(
            f"{', '.join(absent)} not on PATH. The lint, format and acceptance "
            "rungs shell out to these, and the gate records a missing tool as an "
            "environment issue rather than a rejection — so this run would score "
            "by a smaller bar than it declares and nothing in the output would "
            "say so. Run under `uv run --no-sync python tools/bench/"
            "gate_rescore.py`, which puts the project's interpreter and ruff on "
            "PATH."
        )


def preflight(tasks: list[Any], *, gate: Any = None) -> dict[str, Any]:
    """Whether each declared rung can actually reject, per language.

    ``score.rung_report`` is the project's own answer to this and is reused
    whole: it scores the corpus's reference solution (which must pass) and a
    canary built to trip lint and format (which must fail), both through the
    real scoring path. #113's record is three ways this went wrong in one
    afternoon — ruff with no config, eslint absent, eslint present and
    parserless — and every one of them looked healthy from outside.
    """
    return {
        "rungs": score.rung_report(tasks, gate=gate),
        "issues": list(score.preflight(tasks, gate=gate)),
    }


def digest_file(path: Path) -> str:
    """One file's sha256, or ``"absent"`` said out loud."""
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "absent"


def digest_tree(root: Path) -> str:
    """One digest over path-and-content of every file beneath ``root``.

    Paths are inside the hashed text, not only contents, so a candidate renamed
    or dropped moves the digest even when every surviving byte is identical.
    Same construction as ``product.digest`` and for the same reason.
    """
    if not root.is_dir():
        return "absent"
    lines = [
        f"{path.relative_to(root).as_posix()} "
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}"
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def named(measured: Path) -> str:
    """The directory as a repo-relative path, or absolute if it lives outside.

    A committed run is always inside the tree and reads better relative to it. A
    directory elsewhere is named in full rather than refused: a re-score of a
    run held outside the repository is a legitimate thing to do, and failing on
    the *label* would be a strange place to stop.
    """
    try:
        return str(measured.relative_to(REPO))
    except ValueError:
        return str(measured)


def source_identity(measured: Path) -> dict[str, str]:
    """The digest of the run being re-scored: its manifest, rows and candidates.

    A re-score is a claim about a *specific* pile of text. Without this the
    output would name a directory, and a directory is a mutable thing — the
    candidates could be re-dispatched under the same name and the file would
    still look like it described them.
    """
    return {
        "run.json": digest_file(measured / "run.json"),
        "results.jsonl": digest_file(measured / "results.jsonl"),
        "candidates": digest_tree(measured / "candidates"),
    }


def rescore_row(
    row: dict[str, Any], task: Any, candidates: Path, sandbox: Any, *, gate: Any = None
) -> dict[str, Any]:
    """One row's verdict under ``Gate.run``, or the row carried forward and marked."""
    for key in UNSCORED:
        value = row.get(key)
        if value not in (None, "None", ""):
            return dict(row) | {"rescored": False, "rescore_skipped": key}

    candidate = candidates / str(row["task"]) / f"{row['arm']}-{row['draw']}.txt"
    if not candidate.is_file():
        return dict(row) | {"rescored": False, "rescore_skipped": "candidate missing"}

    text = candidate.read_text(encoding="utf-8")
    parsed = parse_reply(
        text,
        output_schema=task.contract.output_schema,
        stop_reason=StopReason(str(row.get("stop_reason", "complete"))),
    )
    if isinstance(parsed, ReplyError):
        # The row says this parsed on the day. If it does not now, the parser
        # moved under us and the two verdicts are not comparable — say so rather
        # than record a rejection no rung produced.
        return dict(row) | {
            "rescored": False,
            "rescore_skipped": f"no longer parses: {parsed.code}",
        }

    started = time.monotonic()
    verdict = score.score(task, parsed.content, sandbox, gate=gate)
    was = str(row.get("passed")).lower() == "true"
    return dict(row) | {
        "rescored": True,
        "passed_before": was,
        "passed": verdict.passed,
        "flipped": verdict.passed != was,
        # The field the source rows do not have, and the reason this tool
        # exists: which rung said no. Named exactly as the live sweep names it
        # (`tools/breadth/measure.py:644`) so one reader serves both files.
        "rejected_by": verdict.rejected_by,
        "rejected_before_acceptance": verdict.rejected_before_acceptance,
        "fail_output": None if verdict.passed else "; ".join(verdict.findings),
        "environment_issues": list(verdict.environment_issues) or None,
        # Named exactly as the live sweep names it, for the same reason the
        # field above is (#261).
        "inconclusive": list(verdict.inconclusive) or None,
        "gate_s": round(time.monotonic() - started, 3),
    }


def rescore_dir(
    measured: Path,
    *,
    write: bool = True,
    tasks: list[Any] | None = None,
    gate: Any = None,
    check_toolchain: bool = True,
) -> dict[str, Any]:
    """Re-score one measurement directory under ``Gate.run``; return its summary.

    ``tasks`` is injectable so this can be driven over hand-built fixture tasks
    whose verdicts are derivable by hand. The default — load the tier the
    manifest names — is what the CLI uses.
    """
    if check_toolchain:
        require_toolchain()
    measured = measured.resolve()
    manifest = json.loads((measured / "run.json").read_text(encoding="utf-8"))
    tier = str(manifest["tier"])
    condition = str(manifest.get("condition", "stock"))
    loaded = breadth.load_tier_tasks(tier) if tasks is None else tasks
    by_id = {task.id: task for task in loaded}
    rows = breadth.read_rows(measured / "results.jsonl")

    retired_path = HERE / "retired.json"
    withdrawn = (
        {
            str(entry["id"])
            for entry in json.loads(retired_path.read_text(encoding="utf-8"))["ids"]
        }
        if retired_path.is_file()
        else set()
    )

    # Grouped by task so one sandbox serves every draw of it, which is what the
    # sweep does (`_task_sandbox`): the workspace, its base commit and the reset
    # are E4's, and paying for them per draw would multiply the cost by the plan.
    order: list[str] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        task_id = str(row["task"])
        if task_id not in grouped:
            grouped[task_id] = []
            order.append(task_id)
        grouped[task_id].append(row)

    rescored: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="mcgyvr-gate-rescore-") as tmp:
        for task_id in order:
            task = by_id.get(task_id)
            if task is None:
                # A retired problem is also "not in tier" — its directory is
                # gone — but naming it keeps the record from reading like a
                # missing file. See tools/bench/retired.json.
                why = "retired" if task_id in withdrawn else "not in tier"
                rescored.extend(
                    dict(row) | {"rescored": False, "rescore_skipped": why}
                    for row in grouped[task_id]
                )
                continue
            ablated = breadth.ablate(task.contract, condition)
            base = score.stage_dir(
                task, ablated.target_content, Path(tmp) / f"{task_id}-base"
            )
            with TempDirSandbox(base) as sandbox:
                for row in grouped[task_id]:
                    rescored.append(
                        rescore_row(
                            row,
                            task,
                            measured / "candidates",
                            sandbox,
                            gate=gate,
                        )
                    )

    summary = summarise(measured, manifest, tier, condition, rows, rescored, loaded)
    if write:
        (measured / ROWS_NAME).write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in rescored),
            encoding="utf-8",
        )
        (measured / SUMMARY_NAME).write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return summary


def bar_of(tasks: list[Any]) -> dict[str, Any] | None:
    """This arm's bar as content, resolved against the staging it is scored in.

    ``breadth.stage_bar`` rather than a local copy, because the whole of #262 is
    that a bar recorded somewhere other than where it is applied describes
    nothing. The same call the dispatching rig makes, from the tool that
    re-scores what the rig produced.
    """
    if not tasks:
        return None
    material, _ = breadth.identity_module.bar_material(
        rungs=score.GATE_RUNGS,
        language=tasks[0].language.name,
        stage_workspace=breadth.stage_bar,
    )
    return material


def summarise(
    measured: Path,
    manifest: dict[str, Any],
    tier: str,
    condition: str,
    rows: list[dict[str, Any]],
    rescored: list[dict[str, Any]],
    tasks: list[Any],
) -> dict[str, Any]:
    """Everything needed to read this re-score, and to produce it again.

    The identity block is not decoration. A re-scored rate is only evidence if a
    reader can say which candidates, which acceptance scripts, which product
    revision and which bar produced it — and can re-run the tool later and see
    either the same rows or exactly what moved.
    """
    graded = [r for r in rescored if r.get("rescored")]
    flips = [r for r in graded if r.get("flipped")]
    lost = [r for r in graded if r.get("passed_before") and not r.get("passed")]
    gained = [r for r in graded if r.get("passed") and not r.get("passed_before")]
    causes = Counter(r["rejected_by"] for r in graded if r.get("rejected_by"))
    skipped = Counter(
        str(r.get("rescore_skipped")) for r in rescored if not r.get("rescored")
    )
    environment = Counter(
        issue for r in graded for issue in (r.get("environment_issues") or ())
    )

    try:
        round_id, product_sha256 = revision.require_pinned()
    except revision.ProductError as exc:  # pragma: no cover — refused at the CLI
        raise RescoreError(str(exc)) from None

    return {
        "directory": named(measured),
        "tier": tier,
        "model": manifest.get("model"),
        "condition": condition,
        "draws": manifest.get("draws"),
        # --- the bar ---------------------------------------------------------
        "scorer": "tools/bench/score.py:score — mcgyvr.gate.runner.Gate.run",
        "gate_rungs": list(score.GATE_RUNGS),
        "gate_semantic": False,
        # Five names are the same five on both arms across a 250-rule Python bar
        # and a 66-rule JS/TS one, so they are not the bar (#262). This is, as
        # content: the resolved rules, the configs that decided them, the tool
        # versions, and the type check neither arm runs. `None` when a resolver
        # would not answer — the tool refuses a degraded environment before this
        # point unless `--allow-degraded` was passed, and that is exactly the
        # caller who should see a null rather than half a bar.
        "bar_resolved": bar_of(tasks),
        "acceptance_timeout_s": score.ACCEPTANCE_TIMEOUT_S,
        "scorer_before": "acceptance command only (predates #113)",
        # Which rungs this run actually exercised, as counts of what rejected.
        # A declared rung that never fires across thousands of candidates is not
        # proof of health, but a rung that fires is proof it was live.
        "rejected_by": dict(sorted(causes.items())),
        # --- run identity (#231 checks 3 and 6) ------------------------------
        "mode": mode.of(manifest),
        "mode_declaration": mode.declare(manifest),
        "round": round_id,
        "product_sha256": product_sha256,
        "round_declaration": revision.declare(
            {"round": round_id, "product_sha256": product_sha256}
        ),
        "source_round_declaration": revision.declare(manifest),
        "source_sha256": source_identity(measured),
        "checkers_sha256": regrade.checker_digests(tier),
        "tasks_in_tier": len(tasks),
        "rescored_at": datetime.now(UTC).isoformat(timespec="seconds"),
        # --- what moved ------------------------------------------------------
        "rows": len(rows),
        "rescored": len(graded),
        "skipped": len(rescored) - len(graded),
        "skipped_why": dict(sorted(skipped.items())),
        "passed_before": sum(1 for r in graded if r["passed_before"]),
        "passed_after": sum(1 for r in graded if r["passed"]),
        "flipped": len(flips),
        "lost": len(lost),
        "gained": len(gained),
        "environment_issues": dict(sorted(environment.items())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-score and report, writing nothing",
    )
    parser.add_argument(
        "--allow-degraded",
        action="store_true",
        help="proceed even though a declared rung cannot reject. The output is "
        "stamped, but it is not comparable with a gate-scored sweep and should "
        "not be laid beside one.",
    )
    args = parser.parse_args(argv)

    try:
        require_toolchain()
    except RescoreError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    # One preflight per tier, before any directory is touched. Cheap next to the
    # run it guards, and the point is to fail before four thousand candidates
    # rather than after them.
    tiers = sorted(
        {
            str(json.loads((d / "run.json").read_text(encoding="utf-8"))["tier"])
            for d in args.directories
        }
    )
    checks: dict[str, Any] = {}
    for tier in tiers:
        checks[tier] = preflight(breadth.load_tier_tasks(tier))
        for issue in checks[tier]["issues"]:
            print(f"preflight {tier}: {issue}", file=sys.stderr)
    degraded = [t for t, c in checks.items() if c["issues"]]
    if degraded and not args.allow_degraded:
        print(
            f"error: the declared rungs cannot all reject on {', '.join(degraded)}. "
            "A rate measured under a silently reduced bar is not comparable with "
            "one that was not, and this whole exercise is a comparison of bars. "
            "Fix the environment, or pass --allow-degraded and read the stamp.",
            file=sys.stderr,
        )
        return 2

    for directory in args.directories:
        summary = rescore_dir(directory, write=not args.check, gate=None)
        summary["preflight"] = checks[summary["tier"]]
        if not args.check:
            (Path(directory).resolve() / SUMMARY_NAME).write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        delta = summary["passed_after"] - summary["passed_before"]
        print(
            f"{summary['directory']}: {summary['passed_before']} -> "
            f"{summary['passed_after']} passing of {summary['rescored']} scored "
            f"({delta:+d}), {summary['skipped']} skipped"
        )
        for rung, count in summary["rejected_by"].items():
            print(f"    rejected at {rung}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
