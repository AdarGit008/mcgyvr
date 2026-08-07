#!/usr/bin/env python3
"""#121/#132 — what breadth is worth when the checker is weaker than ours.

Breadth moves the burden from the model to the checker. One draw and the model
has to be right; eight draws and we only need the check to spot which one is.
So the more draws taken, the more weight the acceptance carries — and the srv1
gains came from tasks that passed one or two draws in eight, which are exactly
the candidates most likely to be "passes the test, still wrong".

Every sweep's acceptance is a hand-written ``accept.mjs`` that pins every
requirement in the contract, and the reference solution passes it. Real
repositories do not have that. Their suites were written to catch regressions,
not to referee eight competing implementations of one change, and #132 records
that we do not know how often a runnable check is declared at all.

This instrument thins the checker and re-selects from candidates already on
disk. No worker is dispatched: the completions were kept by the sweep, so the
only new work is running weaker acceptances over them.

**The thinning rule.** ``accept.mjs`` is split into top-level statements by
bracket depth. A statement that mentions ``assert`` is an assertion; anything
else is setup (imports, fixtures) and is always kept, because dropping it would
break the file rather than weaken it. Strength ``s`` keeps the first ``s``
assertions in file order and drops the rest. Assertion order is the author's,
so the early ones are the obvious cases and the late ones the corners — which
is how a thin real-world suite is thin.

**What comes out.** For each draw budget k and checker strength s, selection is
production's: the first draw that passes the *weak* checker wins (ADR-0008 —
selection is the first gate pass). That winner is then judged by the *full*
checker, which stands in for the truth. Three numbers per cell:

* ``won`` — tasks where the weak checker selected some candidate
* ``true`` — of those, how many the full checker also passes
* ``false`` — of those, how many it does not: the wrong answer we went looking
  for, which is the cost of breadth against a checker that cannot see the
  difference

Usage::

    uv run --no-sync python tools/breadth/selectivity.py \\
        --sweeps records/measurements/.../sweep-d1-T10 [more...] \\
        --out records/measurements/.../selectivity
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import types
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def _measure_rig() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "breadth_measure", HERE / "measure.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


measure = _measure_rig()
bundle = measure.bundle

# Checker strengths as a fraction of the file's assertions, plus the weakest
# check anyone would still call a check: does it run and do the obvious thing.
FRACTIONS = (0.25, 0.5, 0.75, 1.0)


def split_statements(source: str) -> list[str]:
    """Top-level statements, by bracket depth — no JS parser available.

    A statement ends where depth returns to zero at a newline. Good enough for
    the acceptance files, which are flat sequences of calls and const bindings,
    and a test pins the counts it produces for the real ones.
    """
    statements: list[str] = []
    depth = 0
    current: list[str] = []
    in_string: str | None = None
    for line in source.splitlines(keepends=True):
        current.append(line)
        index = 0
        while index < len(line):
            char = line[index]
            if in_string:
                if char == "\\":
                    index += 2
                    continue
                if char == in_string:
                    in_string = None
            elif char in "\"'`":
                in_string = char
            elif char in "([{":
                depth += 1
            elif char in ")]}":
                depth -= 1
            index += 1
        if depth <= 0 and line.strip():
            statements.append("".join(current))
            current = []
    if current:
        statements.append("".join(current))
    return statements


def thin(source: str, keep: int) -> str:
    """The acceptance with only its first ``keep`` assertions left standing."""
    kept: list[str] = []
    seen = 0
    for statement in split_statements(source):
        if "assert" in statement and not statement.lstrip().startswith("import"):
            seen += 1
            if seen > keep:
                continue
        kept.append(statement)
    return "".join(kept)


def declared_command(task: Any) -> str:
    """The one runnable check a task declares, from either slot.

    Since #183 a contract states its check in ``demonstration`` when the
    evidence is expected to fail at baseline and in ``acceptance`` when it is
    expected to pass — the bug-fix tasks moved to the former. Both are the
    same command to run, and this rig only ever needs the first, so it reads
    them in the order the bundle rig executes them rather than assuming a slot.
    """
    for command in (*task.contract.demonstration, *task.contract.acceptance):
        return str(command)
    raise bundle.MeasureError(
        f"{task.id} declares no runnable check in either slot — there is "
        "nothing for a thinned checker to be a thinning of"
    )


def count_assertions(source: str) -> int:
    return sum(
        1
        for statement in split_statements(source)
        if "assert" in statement and not statement.lstrip().startswith("import")
    )


def _judge(job: tuple[str, str, str, str]) -> tuple[str, bool]:
    """One candidate against one thinned acceptance, in its own temp tree."""
    key, content, accept_source, command = job
    with tempfile.TemporaryDirectory(prefix="mcgyvr-selectivity-") as tmp:
        # The thinned acceptance is staged outside the work tree, because
        # run_acceptance copies it in and copying a file onto itself is an
        # error rather than a no-op.
        stage = Path(tmp) / "stage"
        stage.mkdir()
        accept = stage / "accept.mjs"
        accept.write_text(accept_source, encoding="utf-8")
        task = types.SimpleNamespace(
            accept=accept,
            # Both slots, because run_acceptance runs demonstration first and
            # then acceptance; the thinned file is the whole check either way.
            contract=types.SimpleNamespace(demonstration=[], acceptance=[command]),
        )
        verdict = bundle.run_acceptance(task, content, Path(tmp) / "work")
    return key, bool(verdict.passed)


def candidates_of(sweep: Path, draws: int) -> dict[tuple[str, int], str]:
    """The parsed file content of every sampled draw the sweep kept."""
    out: dict[tuple[str, int], str] = {}
    for task_dir in sorted((sweep / "candidates").iterdir()):
        for draw in range(draws):
            path = task_dir / f"sampled-{draw}.txt"
            if not path.is_file():
                continue
            parsed = measure.parse_reply(path.read_text(encoding="utf-8"))
            if isinstance(parsed, measure.ReplyError):
                continue
            out[(task_dir.name, draw)] = parsed.content
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sweeps", nargs="+", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tier", default="d1")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    tasks = {task.id: task for task in measure.load_tier_tasks(args.tier)}
    sources = {
        task_id: task.accept.read_text(encoding="utf-8")
        for task_id, task in tasks.items()
    }
    totals = {task_id: count_assertions(source) for task_id, source in sources.items()}

    args.out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"strengths": list(FRACTIONS), "sweeps": {}}

    for sweep in args.sweeps:
        manifest = json.loads((sweep / "run.json").read_text(encoding="utf-8"))
        draws = int(manifest["draws"])
        parsed = candidates_of(sweep, draws)
        print(f"{sweep}: {len(parsed)} parseable candidates", file=sys.stderr)

        jobs: list[tuple[str, str, str, str]] = []
        for fraction in FRACTIONS:
            for (task_id, draw), content in parsed.items():
                keep = max(1, round(totals[task_id] * fraction))
                command = declared_command(tasks[task_id])
                jobs.append(
                    (
                        f"{fraction}|{task_id}|{draw}",
                        content,
                        thin(sources[task_id], keep),
                        command,
                    )
                )

        verdicts: dict[str, bool] = {}
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for key, ok in pool.map(_judge, jobs, chunksize=8):
                verdicts[key] = ok

        cells: dict[str, Any] = {}
        for fraction in FRACTIONS:
            per_k = []
            for k in range(1, draws + 1):
                won = true = false = 0
                for task_id in sorted(tasks):
                    for draw in range(k):
                        if verdicts.get(f"{fraction}|{task_id}|{draw}"):
                            won += 1
                            if verdicts.get(f"1.0|{task_id}|{draw}"):
                                true += 1
                            else:
                                false += 1
                            break
                per_k.append({"k": k, "won": won, "true": true, "false": false})
            cells[str(fraction)] = per_k
        # The full-strength re-run must reproduce the sweep's own verdicts. If
        # it does not, the thinning harness is measuring itself rather than the
        # checker, and every weaker cell beside it is worthless.
        agree = disagree = 0
        for line in (sweep / "results.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["arm"] != "sampled" or row.get("parse_error"):
                continue
            recomputed = verdicts.get(f"1.0|{row['task']}|{row['draw']}")
            if recomputed is None:
                continue
            if recomputed == bool(row.get("passed")):
                agree += 1
            else:
                disagree += 1

        report["sweeps"][str(sweep)] = {
            "draws": draws,
            "model": manifest["model"],
            "sampled_temperature": manifest.get("sampled_temperature"),
            "assertions": totals,
            "full_strength_agrees_with_the_sweep": {
                "agree": agree,
                "disagree": disagree,
            },
            "cells": cells,
        }

    (args.out / "selectivity.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["sweeps"], indent=2)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
