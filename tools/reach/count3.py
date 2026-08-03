#!/usr/bin/env python3
"""Count 3 — false positives: the candidate resolver over code that shipped.

    python tools/reach/count3.py --run
    python tools/reach/count3.py --summarise

This is the number that decides whether the rung **blocks or only reports**. A
resolver that flags correct code is worse than no resolver: it converts a green
check into an argument, and the cost lands on every change rather than on the
ones it catches. CLM-0006 established that ghostcall is real and that its engine
is stdlib-only; it deliberately did not establish that it is the right resolver,
and nothing here should be read as having chosen it before this ran.

**Counted the same way as Counts 1 and 2** — over the same corpus, per change,
restricted to the lines that change added. The rung judges added lines
(``gate/changeset.py``), so a flag on a line the change did not touch is not a
verdict the rung would ever have rendered. The whole-file rate is recorded
beside it, because a rung that checked whole files would face that one instead,
and the two differ by a lot.

**Why a flag here counts as a false positive, and the limit of that.** Every
file measured shipped: it passed a declared, human-gated check on a protected
branch, which is the corpus's proxy for "accepted". Under that proxy a
``hallucinated`` verdict on shipped code is a false positive. The proxy is not
proof — shipped code can carry a latent bug, and a flag could be right — so
these are *presumptive* false positives, and any that appear are listed
individually with their line so the presumption can be checked by hand rather
than taken on report.

**``module_missing`` is not a false positive and must not be counted as one.**
It means the resolver could not import a root at all, which is an environment
outcome, not a verdict about the code. It is counted separately and loudly,
because it is the failure mode that would make the rung *vacuous* rather than
wrong: a rung whose imports all fail flags nothing and passes everything.

**Python frames only.** ghostcall parses Python, so the immer frame is out of
scope here and its 27 changes are not in this count's denominator. Two of three
frames, and the JS/TS half of the launch languages has no candidate measured.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import frames
from frames import FrameContainer

OUT_DIR = frames.REPO / "records" / "measurements" / "reach-2026-08-03"
ROWS = OUT_DIR / "count3-falsepos.jsonl"
CLONES = Path("/tmp/reach-clones")
SCRATCH = Path("/tmp/reach-run")
GHOSTCALL = frames.REPO / "records" / "evidence" / "ghostcall-2026-08-02" / "src"

PYTHON_FRAMES = ("AdarGit008/mcgyvr", "pallets/click")

# Runs inside the container, with the frame's own environment importable and
# the vendored ghostcall on the path. Kept as a file rather than a -c string so
# a failure has a traceback with line numbers.
_DRIVER = """
import json, sys
from pathlib import Path
from ghostcall.parser import parse
from ghostcall.checker import check

targets = json.loads(Path(sys.argv[1]).read_text())
out = []
for path in targets:
    source_path = Path(path)
    try:
        source = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        out.append({"path": path, "error": f"unreadable: {exc}"})
        continue
    try:
        parsed = parse(source)
    except SyntaxError as exc:
        out.append({"path": path, "error": f"syntax: {exc}"})
        continue
    calls = []
    for call in parsed.calls:
        result = check(call)
        calls.append({
            "line": call.lineno,
            "chain": call.resolved_display,
            "status": result.status,
            "missing_attr": result.missing_attr,
        })
    out.append({"path": path, "calls": calls})
Path(sys.argv[2]).write_text(json.dumps(out))
"""


def measure_frame(frame: Mapping) -> list[dict]:
    runtime = frames.FRAME_RUNTIME[frame["repo"]]
    clone = frames.prepare_clone(frame, CLONES)
    tag = f"reach-{frame['repo'].split('/')[-1].lower()}"
    frames.build_image(runtime, tag)

    slug = frame["repo"].replace("/", "_")
    out = SCRATCH / slug
    cache = SCRATCH / "cache" / slug
    out.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)

    # The vendored engine, staged where the container can see it. Copied rather
    # than mounted from records/ so nothing in the run can write to the evidence.
    staged = cache / "ghostcall-src"
    shutil.rmtree(staged, ignore_errors=True)
    shutil.copytree(GHOSTCALL, staged)
    (cache / "driver.py").write_text(_DRIVER, encoding="utf-8")

    env = {**runtime.env, "PYTHONPATH": "/cache/ghostcall-src"}
    result_path = out / "count3.json"
    targets_path = cache / "targets.json"
    rows: list[dict] = []

    with FrameContainer(tag, clone, out, cache) as container:
        provisioned: str | None = None
        for index, change in enumerate(frame["changes"], start=1):
            commit = change["commit"]
            frames.checkout(clone, commit, runtime.keep)
            added = frames.added_lines(
                clone, commit, frame["unit"], frame["source_glob"]
            )
            digest = _digest(clone, runtime)
            if digest != provisioned:
                container.run(runtime.provision, runtime.env)
                provisioned = digest

            targets_path.write_text(json.dumps(sorted(added)), encoding="utf-8")
            result_path.unlink(missing_ok=True)
            code, output = container.run(
                "uv run --frozen python /cache/driver.py "
                "/cache/targets.json /out/count3.json",
                env,
            )
            if not result_path.is_file():
                rows.append(
                    {
                        "frame": frame["repo"],
                        "commit": commit,
                        "date": change["date"],
                        "measured": False,
                        "note": f"driver produced no output (exit {code}): "
                        f"{output[-400:]}",
                    }
                )
                print(f"  [{index}] {commit[:9]} DRIVER FAILED", file=sys.stderr)
                continue

            rows.append(_row(frame, change, added, json.loads(result_path.read_text())))
            last = rows[-1]
            print(
                f"  [{index:>2}/{len(frame['changes'])}] {commit[:9]} "
                f"calls {last['calls_on_added_lines']:<5} "
                f"flagged {last['hallucinated_on_added_lines']:<3} "
                f"module_missing {last['module_missing_on_added_lines']}",
                file=sys.stderr,
            )
    return rows


def _digest(clone: Path, runtime: frames.FrameRuntime) -> str:
    import hashlib

    digest = hashlib.sha256()
    for name in runtime.manifests:
        path = clone / name
        digest.update(name.encode())
        digest.update(path.read_bytes() if path.is_file() else b"<absent>")
    return digest.hexdigest()


def _row(
    frame: Mapping,
    change: Mapping,
    added: Mapping[str, frozenset[int]],
    report: list[dict],
) -> dict:
    totals = {
        "calls_in_files": 0,
        "calls_on_added_lines": 0,
        "hallucinated_in_files": 0,
        "hallucinated_on_added_lines": 0,
        "module_missing_in_files": 0,
        "module_missing_on_added_lines": 0,
        "dynamic_on_added_lines": 0,
    }
    flags: list[dict] = []
    errors: list[dict] = []
    missing_roots: set[str] = set()
    for entry in report:
        if "error" in entry:
            errors.append(entry)
            continue
        lines = added.get(entry["path"], frozenset())
        for call in entry["calls"]:
            on_added = call["line"] in lines
            totals["calls_in_files"] += 1
            totals["calls_on_added_lines"] += 1 if on_added else 0
            if call["status"] == "hallucinated":
                totals["hallucinated_in_files"] += 1
                totals["hallucinated_on_added_lines"] += 1 if on_added else 0
                # EVERY flag is recorded, not only the ones on added lines. A
                # whole-file count with no calls behind it asks the reader to
                # take the verdict on trust, which is the thing ADR-0004 exists
                # to refuse — and the flags off the added lines are the only
                # evidence this corpus yields about what the resolver actually
                # objects to.
                flags.append(
                    {
                        "path": entry["path"],
                        "line": call["line"],
                        "chain": call["chain"],
                        "missing_attr": call["missing_attr"],
                        "on_added_line": on_added,
                    }
                )
            elif call["status"] == "module_missing":
                totals["module_missing_in_files"] += 1
                totals["module_missing_on_added_lines"] += 1 if on_added else 0
                missing_roots.add(call["missing_attr"] or "")
            elif call["status"] == "dynamic" and on_added:
                totals["dynamic_on_added_lines"] += 1

    return {
        "frame": frame["repo"],
        "commit": change["commit"],
        "date": change["date"],
        "measured": True,
        "files": len(report),
        "added_source_lines": change["added_source_lines"],
        **totals,
        "flags": flags,
        "unimportable_roots": sorted(missing_roots),
        "errors": errors,
    }


def summarise(rows: list[dict]) -> dict:
    by_frame: dict[str, dict] = {}
    keys = (
        "calls_in_files",
        "calls_on_added_lines",
        "hallucinated_in_files",
        "hallucinated_on_added_lines",
        "module_missing_in_files",
        "module_missing_on_added_lines",
        "dynamic_on_added_lines",
    )
    for row in rows:
        frame = by_frame.setdefault(
            row["frame"],
            {"changes": 0, "measured": 0, "flags": [], **dict.fromkeys(keys, 0)},
        )
        frame["changes"] += 1
        if not row.get("measured"):
            continue
        frame["measured"] += 1
        for key in keys:
            frame[key] += row[key]
        frame["flags"].extend({**f, "commit": row["commit"][:9]} for f in row["flags"])

    for frame in by_frame.values():
        calls = frame["calls_on_added_lines"]
        frame["false_positive_rate_on_added_lines"] = (
            round(100 * frame["hallucinated_on_added_lines"] / calls, 3)
            if calls
            else None
        )
    return by_frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--summarise", action="store_true")
    args = parser.parse_args()
    if args.run == args.summarise:
        parser.error("pass exactly one of --run / --summarise")

    if args.summarise:
        rows = [json.loads(line) for line in ROWS.read_text().splitlines() if line]
        print(json.dumps(summarise(rows), indent=2, sort_keys=True))
        return 0

    corpus = frames.load_corpus()
    rows: list[dict] = []
    for frame in corpus["frames"]:
        if frame["repo"] not in PYTHON_FRAMES:
            print(f"{frame['repo']} — skipped, not Python", file=sys.stderr)
            continue
        print(f"{frame['repo']} — {len(frame['changes'])} changes", file=sys.stderr)
        rows.extend(measure_frame(frame))

    frames.write_jsonl(ROWS, rows)
    print(json.dumps(summarise(rows), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
