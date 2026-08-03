#!/usr/bin/env python3
"""Count 2 — absence: how often no runnable check is declared at all.

    python tools/reach/count2.py --run
    python tools/reach/count2.py --summarise

This is the count that decides whether the rung is an *increment* or the only
thing there is. Where a repository declares nothing runnable, mcgyvr cannot
express a task at all today: ``contract.py`` rejects a contract at load when its
type needs acceptance commands and none are given, over
``TaskType.needs_acceptance_commands``. So an absent declaration is not a weaker
gate, it is an unreachable task type, and the rung is what would make it
reachable.

**Declared, never inferred.** A check counts only if the repository states it in
a file whose purpose is to state it — a pytest section, a Makefile target, a
``scripts.test`` entry, a CI workflow step. "There is a ``tests/`` directory" is
not a declaration: nothing there tells a runner what to execute, and treating a
convention as a declaration is how a measurement quietly assumes its own answer.
Every hit records which file and which signal produced it, so a reader can
disagree with a specific line rather than with the total.

**Evaluated at each commit, not once per repository.** A repository that
declares a suite today may not have when a given change landed, and the rung
would have faced whatever was declared at the time. Doing it per commit costs
nothing here — it is git metadata only, no container, no execution.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import frames

OUT_DIR = frames.REPO / "records" / "measurements" / "reach-2026-08-03"
ROWS = OUT_DIR / "count2-absence.jsonl"
CLONES = Path("/tmp/reach-clones")

# The npm placeholder `npm init` writes. It exits non-zero and runs nothing, so
# counting it as a declared check would be counting the absence of one.
_NPM_PLACEHOLDER = "no test specified"


def blob(clone: Path, commit: str, path: str) -> str | None:
    """A file's content at a commit, or None when it is not in that tree."""
    proc = frames.subprocess.run(
        ["git", "-C", str(clone), "show", f"{commit}:{path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout if proc.returncode == 0 else None


def _tree(clone: Path, commit: str) -> list[str]:
    out = frames.git(clone, "ls-tree", "-r", "--name-only", commit)
    return [p for p in out.split("\n") if p]


def declarations(clone: Path, commit: str) -> list[dict[str, str]]:
    """Every runnable-check declaration present in a commit's tree.

    Ordered from the most specific statement of "run this" to the least, but
    all of them count equally: the question is whether anything runnable is
    declared, not which is canonical.
    """
    found: list[dict[str, str]] = []
    paths = set(_tree(clone, commit))

    def add(where: str, signal: str) -> None:
        found.append({"file": where, "signal": signal})

    # --- Python -----------------------------------------------------------
    if "pyproject.toml" in paths:
        raw = blob(clone, commit, "pyproject.toml") or ""
        try:
            data = tomllib.loads(raw)
        except tomllib.TOMLDecodeError:
            data = {}
        tool = data.get("tool", {}) if isinstance(data, dict) else {}
        if isinstance(tool, dict):
            if "pytest" in tool:
                add("pyproject.toml", "[tool.pytest.ini_options]")
            if "coverage" in tool:
                add("pyproject.toml", "[tool.coverage]")
    for name, signal in (
        ("pytest.ini", "pytest.ini present"),
        ("tox.ini", "tox.ini present"),
        ("noxfile.py", "noxfile.py present"),
        ("setup.cfg", "setup.cfg [tool:pytest]"),
    ):
        if name not in paths:
            continue
        if name == "setup.cfg" and "[tool:pytest]" not in (
            blob(clone, commit, name) or ""
        ):
            continue
        add(name, signal)

    # --- Make -------------------------------------------------------------
    if "Makefile" in paths:
        text = blob(clone, commit, "Makefile") or ""
        for line in text.split("\n"):
            if line.startswith(("test:", "test :", "check:", "check :")):
                add("Makefile", f"target {line.split(':')[0].strip()!r}")
                break

    # --- Node -------------------------------------------------------------
    if "package.json" in paths:
        try:
            package = json.loads(blob(clone, commit, "package.json") or "{}")
        except json.JSONDecodeError:
            package = {}
        scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
        if isinstance(scripts, dict):
            command = str(scripts.get("test", ""))
            if command and _NPM_PLACEHOLDER not in command:
                add("package.json", "scripts.test")
            if "coverage" in scripts:
                add("package.json", "scripts.coverage")

    # --- CI ---------------------------------------------------------------
    for path in sorted(p for p in paths if p.startswith(".github/workflows/")):
        text = (blob(clone, commit, path) or "").lower()
        if any(k in text for k in ("pytest", "vitest", "npm test", "yarn test", "tox")):
            add(path, "workflow runs a test command")
            break

    return found


def measure_frame(frame: Mapping) -> list[dict]:
    clone = frames.prepare_clone(frame, CLONES)
    rows = []
    for change in frame["changes"]:
        commit = change["commit"]
        found = declarations(clone, commit)
        rows.append(
            {
                "frame": frame["repo"],
                "commit": commit,
                "date": change["date"],
                "declared": bool(found),
                "signals": found,
            }
        )
    return rows


def summarise(rows: list[dict]) -> dict:
    by_frame: dict[str, dict] = {}
    for row in rows:
        frame = by_frame.setdefault(
            row["frame"], {"commits": 0, "commits_without_declaration": 0}
        )
        frame["commits"] += 1
        if not row["declared"]:
            frame["commits_without_declaration"] += 1

    total = sum(f["commits"] for f in by_frame.values())
    absent = sum(f["commits_without_declaration"] for f in by_frame.values())
    repos_absent = sum(
        1 for f in by_frame.values() if f["commits_without_declaration"] == f["commits"]
    )
    return {
        "per_frame": by_frame,
        "pooled": {
            "repositories": len(by_frame),
            "repositories_with_no_declaration_ever": repos_absent,
            "commits": total,
            "commits_without_declaration": absent,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--summarise", action="store_true")
    args = parser.parse_args()
    if args.run == args.summarise:
        parser.error("pass exactly one of --run / --summarise")

    if args.summarise:
        rows = [json.loads(line) for line in ROWS.read_text().splitlines() if line]
    else:
        corpus = frames.load_corpus()
        rows = []
        for frame in corpus["frames"]:
            print(f"{frame['repo']} — {len(frame['changes'])} commits", file=sys.stderr)
            rows.extend(measure_frame(frame))
        frames.write_jsonl(ROWS, rows)

    print(json.dumps(summarise(rows), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
