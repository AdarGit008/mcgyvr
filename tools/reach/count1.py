#!/usr/bin/env python3
"""Count 1 — reach: added source lines the declared checks never execute.

    python tools/reach/count1.py --run        # measure (needs Docker)
    python tools/reach/count1.py --summarise  # re-derive totals from the rows

**Measured at each change's own commit, not once per frame.** A line number
only means something in the tree that contains it, and the rung's question is
posed at the moment a change is proposed: these checks, against this tree, do
they reach what this change added? Running the suite once at the frame's tip and
mapping old line numbers forward would answer a different question and would put
a line-tracking heuristic between the corpus and the number. So the suite runs
77 times, which the frames make affordable — under a minute of container time
per commit for all three.

**Four outcomes per added line, not two.** An added line is *reached* if the
instrument saw it execute, *unreached* if the instrument considered it
executable and it never ran, *non-executable* if it is a blank line, a comment
or something the instrument excludes, and *not reported* if its file never
appeared in the report at all. Folding the last two into "unreached" is what
turns this measurement into a bigger, wronger number: a comment was never going
to execute, and counting it as unreached inflates the gap that #123 is being
sized against. The headline is therefore over executable added lines, and the
remainder is printed beside it rather than absorbed.

**A suite that fails still executed lines.** Exit status is recorded per commit
and reported, but a non-zero suite is not silently dropped: the question is what
the declared check *ran*, and a check with one failing test ran nearly all of it.
What is excluded — loudly, with a reason — is a commit that produced no report at
all, because there the instrument, not the repository, is what failed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import frames
from frames import FrameContainer, FrameRuntime, ReachError

OUT_DIR = frames.REPO / "records" / "measurements" / "reach-2026-08-03"
ROWS = OUT_DIR / "count1-reach.jsonl"
CLONES = Path("/tmp/reach-clones")
SCRATCH = Path("/tmp/reach-run")


def manifest_digest(clone: Path, runtime: FrameRuntime) -> str:
    """Fingerprint the dependency-defining files in the current checkout.

    Re-provisioning per commit would multiply the run time by the install cost
    for no gain; provisioning only when this changes is the same cache key
    :mod:`mcgyvr.sandbox.image` uses (#29), applied to a mounted tree.
    """
    digest = hashlib.sha256()
    for name in runtime.manifests:
        path = clone / name
        digest.update(name.encode())
        digest.update(path.read_bytes() if path.is_file() else b"<absent>")
    return digest.hexdigest()


def declared_coverage(clone: Path) -> str:
    """What the repository declared as its coverage instrument *at this commit*.

    ``corpus.json`` records one ``declared_check`` per frame, read at the pinned
    tip. A frame's history does not have to agree with its tip, and immer's does
    not: at ten of its twenty-seven pinned commits ``scripts.coverage`` is
    ``jest --coverage``, because the project had not migrated to vitest yet.
    Running the tip's command at those commits would be running something the
    repository never declared *then* — the same substitution ADR-0006 forbids,
    arriving through time rather than through a detector. Recording the
    per-commit declaration puts that in the rows instead of in a footnote.
    """
    package = clone / "package.json"
    if package.is_file():
        try:
            data = json.loads(package.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return ""
        scripts = data.get("scripts", {}) if isinstance(data, dict) else {}
        return str(scripts.get("coverage", "")) if isinstance(scripts, dict) else ""
    pyproject = clone / "pyproject.toml"
    if pyproject.is_file():
        text = pyproject.read_text(encoding="utf-8", errors="replace")
        return "[tool.coverage]" if "[tool.coverage" in text else ""
    return ""


def suite_summary(output: str) -> str:
    """The runner's own last word on how many tests passed and failed.

    A non-zero suite is kept rather than dropped, which is only defensible if
    the reader can see *how* non-zero: "1 failed, 1940 passed" and "600 failed,
    1341 passed" both exit 1, and they imply very different things about how
    much of the added code the check actually got to. Taken from the runner's
    own summary line rather than recounted, so it says what the repository's
    tooling says.
    """
    for line in reversed(output.strip().split("\n")):
        lowered = line.lower()
        if any(k in lowered for k in ("passed", "failed", "error", "no tests")):
            return line.strip()[:200]
    return ""


def classify(
    added: Mapping[str, frozenset[int]], report: Mapping[str, frames.FileCoverage]
) -> tuple[list[dict], dict[str, int]]:
    """Split each file's added lines four ways against the coverage report."""
    files: list[dict] = []
    totals = {
        "added": 0,
        "reached": 0,
        "unreached": 0,
        "non_executable": 0,
        "not_reported": 0,
    }
    for path in sorted(added):
        lines = added[path]
        coverage = report.get(path)
        if coverage is None:
            entry = {
                "path": path,
                "added": len(lines),
                "reached": 0,
                "unreached": 0,
                "non_executable": 0,
                "not_reported": len(lines),
            }
        else:
            reached = lines & coverage.executed
            executable = lines & coverage.executable
            entry = {
                "path": path,
                "added": len(lines),
                "reached": len(reached),
                "unreached": len(executable - reached),
                "non_executable": len(lines - executable),
                "not_reported": 0,
            }
        files.append(entry)
        for key in totals:
            totals[key] += entry[key]
    return files, totals


def measure_frame(frame: Mapping, runtime: FrameRuntime) -> list[dict]:
    clone = frames.prepare_clone(frame, CLONES)
    tag = f"reach-{frame['repo'].split('/')[-1].lower()}"
    frames.build_image(runtime, tag)

    out = SCRATCH / frame["repo"].replace("/", "_")
    cache = SCRATCH / "cache" / frame["repo"].replace("/", "_")
    report_path = out / "coverage.json"
    rows: list[dict] = []

    with FrameContainer(tag, clone, out, cache) as container:
        provisioned: str | None = None
        for index, change in enumerate(frame["changes"], start=1):
            commit = change["commit"]
            frames.checkout(clone, commit, runtime.keep)
            added = frames.added_lines(
                clone, commit, frame["unit"], frame["source_glob"]
            )
            recomputed = sum(len(v) for v in added.values())
            if recomputed != change["added_source_lines"]:
                raise ReachError(
                    f"{frame['repo']} {commit[:9]}: recomputed {recomputed} added "
                    f"lines but the corpus pins {change['added_source_lines']} — "
                    "the numerator and the denominator have diverged."
                )

            digest = manifest_digest(clone, runtime)
            provision_note = ""
            if digest != provisioned:
                code, output = container.run(runtime.provision, runtime.env)
                if code != 0:
                    provision_note = f"provision failed ({code}): {output[-400:]}"
                provisioned = digest

            # Wipe the WHOLE output directory, not just the report path. An
            # instrument that writes through an intermediate directory
            # (vitest's --coverage.reportsDirectory) leaves last commit's file
            # there, and a report step that copies it will happily copy stale
            # data over a run that never happened. Ten immer rows were the
            # previous commit's coverage before this existed.
            for stale in out.glob("*"):
                if stale.is_dir():
                    shutil.rmtree(stale, ignore_errors=True)
                else:
                    stale.unlink(missing_ok=True)
            started = time.monotonic()
            code, output = container.run(runtime.instrument, runtime.env)
            container.run(runtime.report_cmd, runtime.env)
            elapsed = round(time.monotonic() - started, 1)

            if report_path.is_file():
                report = frames.load_report(runtime.report_kind, report_path)
                files, totals = classify(added, report)
                note = provision_note
            else:
                files, totals = (
                    [],
                    dict.fromkeys(
                        (
                            "added",
                            "reached",
                            "unreached",
                            "non_executable",
                            "not_reported",
                        ),
                        0,
                    ),
                )
                totals["added"] = recomputed
                note = (
                    provision_note
                    or f"no coverage report produced (exit {code}): {output[-400:]}"
                )

            rows.append(
                {
                    "frame": frame["repo"],
                    "commit": commit,
                    "date": change["date"],
                    "added_source_lines": change["added_source_lines"],
                    "suite_exit": code,
                    "suite_summary": suite_summary(output),
                    "declared_coverage_at_commit": declared_coverage(clone),
                    "report_present": report_path.is_file(),
                    "seconds": elapsed,
                    "totals": totals,
                    "files": files,
                    "note": note,
                }
            )
            state = "ok" if report_path.is_file() else "NO REPORT"
            print(
                f"  [{index:>2}/{len(frame['changes'])}] {commit[:9]} "
                f"+{recomputed:<5} reached {totals['reached']:<5} "
                f"unreached {totals['unreached']:<5} {elapsed:>5}s  {state}",
                file=sys.stderr,
            )
    return rows


def summarise(rows: list[dict]) -> dict:
    """Per-frame totals, and a pooled figure that carries its split."""
    by_frame: dict[str, dict] = {}
    for row in rows:
        frame = by_frame.setdefault(
            row["frame"],
            {
                "changes": 0,
                "measured": 0,
                "suite_nonzero": 0,
                "added": 0,
                "reached": 0,
                "unreached": 0,
                "non_executable": 0,
                "not_reported": 0,
                "unmeasured_changes": [],
                "declared_coverage_at_commit": {},
            },
        )
        frame["changes"] += 1
        # Counted for every change, measured or not: a frame whose declaration
        # changed mid-history is the reason some of its changes are unmeasurable,
        # and the two facts have to be readable side by side.
        declaration = row.get("declared_coverage_at_commit", "")
        frame["declared_coverage_at_commit"][declaration] = (
            frame["declared_coverage_at_commit"].get(declaration, 0) + 1
        )
        if not row["report_present"]:
            frame["unmeasured_changes"].append(
                {
                    "commit": row["commit"][:9],
                    "date": row["date"],
                    "added_source_lines": row["added_source_lines"],
                    "declared_coverage_at_commit": declaration,
                    "why": row["note"][:160],
                }
            )
            continue
        frame["measured"] += 1
        frame["suite_nonzero"] += 1 if row["suite_exit"] != 0 else 0
        for key in ("added", "reached", "unreached", "non_executable", "not_reported"):
            frame[key] += row["totals"][key]

    for frame in by_frame.values():
        executable = frame["reached"] + frame["unreached"]
        never = frame["unreached"] + frame["not_reported"]
        frame["executable_added"] = executable
        frame["never_executed"] = never
        frame["unreached_pct_of_executable"] = (
            round(100 * frame["unreached"] / executable, 1) if executable else None
        )
        frame["never_executed_pct_of_added"] = (
            round(100 * never / frame["added"], 1) if frame["added"] else None
        )
        # What share of the pinned denominator this frame's figures actually
        # cover. A percentage computed over 17 of 27 changes is not a statement
        # about the frame unless the 17 is printed with it.
        frame["coverage_of_frame_pct"] = round(
            100 * frame["measured"] / frame["changes"], 1
        )
    return by_frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="measure (needs Docker)")
    parser.add_argument(
        "--summarise", action="store_true", help="re-derive totals from the rows"
    )
    parser.add_argument("--frame", help="measure only this frame")
    args = parser.parse_args()
    if args.run == args.summarise:
        parser.error("pass exactly one of --run / --summarise")

    if args.summarise:
        rows = [json.loads(line) for line in ROWS.read_text().splitlines() if line]
        print(json.dumps(summarise(rows), indent=2, sort_keys=True))
        return 0

    corpus = frames.load_corpus()
    existing = {}
    if ROWS.is_file():
        for line in ROWS.read_text().splitlines():
            if line:
                row = json.loads(line)
                existing[(row["frame"], row["commit"])] = row

    rows: list[dict] = []
    for frame in corpus["frames"]:
        if args.frame and frame["repo"] != args.frame:
            rows.extend(row for key, row in existing.items() if key[0] == frame["repo"])
            continue
        print(f"{frame['repo']} — {len(frame['changes'])} changes", file=sys.stderr)
        rows.extend(measure_frame(frame, frames.FRAME_RUNTIME[frame["repo"]]))

    order = {f["repo"]: i for i, f in enumerate(corpus["frames"])}
    rows.sort(key=lambda r: (order[r["frame"]], r["commit"]))
    frames.write_jsonl(ROWS, rows)
    print(json.dumps(summarise(rows), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
