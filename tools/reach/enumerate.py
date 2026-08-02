#!/usr/bin/env python3
"""Re-enumerate the #125 reach corpus and check it against the pinned copy.

The corpus is only evidence if it reproduces. This walks the same frames from
the same pinned commits and either prints the result or diffs it against
``records/corpora/reach-2026-08-02/corpus.json``.

    python tools/reach/enumerate.py --check     # exit 1 on any drift
    python tools/reach/enumerate.py --write     # regenerate the pinned copy

External frames are fetched at their pinned sha rather than at whatever the
default branch holds now, which is the whole point of pinning them. Nothing in
a fetched repository is executed: this reads git metadata only, so it stays on
the right side of ADR-0005 without needing a sandbox. The counts that DO
require running a target's test suite are Count 1's, and they do not live here.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
CORPUS = REPO / "records" / "corpora" / "reach-2026-08-02" / "corpus.json"

CLONE_DEPTH = 120
REMOTES = {
    "pallets/click": "https://github.com/pallets/click.git",
    "immerjs/immer": "https://github.com/immerjs/immer.git",
}


def git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {cwd}: {proc.stderr.strip()}"
        )
    return proc.stdout


def matches(path: str, glob: str) -> bool:
    """``src/**/*.py`` — the only shape the corpus uses, matched without fnmatch.

    fnmatch has no ``**`` and would let ``src/a/b.py`` past a ``src/*.py``
    pattern on some platforms; spelling it out keeps the frames honest.
    """
    prefix, _, suffix = glob.partition("**/*")
    return path.startswith(prefix) and path.endswith(suffix)


def walk(cwd: Path, rev: str, unit: str, glob: str, limit: int) -> list[dict]:
    """The frame's qualifying changes, newest first."""
    first_parent = unit.startswith("first-parent")
    log = ["log", rev, "--format=%H%x1f%ci%x1f%s"]
    log += (
        ["--first-parent", "--merges"] if first_parent else ["--no-merges", "-n", "400"]
    )

    out: list[dict] = []
    for line in git(cwd, *log).strip().split("\n"):
        if not line:
            continue
        sha, date, subject = line.split("\x1f")
        parent = f"{sha}^1" if first_parent else f"{sha}^"
        try:
            numstat = git(cwd, "diff", "--numstat", parent, sha)
        except RuntimeError:
            continue  # a shallow clone's boundary commit has no parent here
        added, files = 0, []
        for row in filter(None, numstat.split("\n")):
            parts = row.split("\t")
            if len(parts) != 3:
                continue
            count, _, path = parts
            if count == "-" or not matches(path, glob):
                continue  # "-" is a binary change: no line attribution exists
            if int(count):
                added += int(count)
                files.append(path)
        if not added:
            continue
        out.append(
            {
                "commit": sha,
                "date": date[:10],
                "subject": subject[:90],
                "added_source_lines": added,
                "source_files": sorted(set(files)),
            }
        )
        if len(out) >= limit:
            break
    return out


def fetch_pinned(remote: str, sha: str, dest: Path) -> Path:
    """Materialise exactly the pinned commit, not the current default branch."""
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--quiet", str(dest)], check=True)
    git(dest, "remote", "add", "origin", remote)
    git(dest, "fetch", "--quiet", "--depth", str(CLONE_DEPTH), "origin", sha)
    return dest


def rebuild(pinned: dict, workdir: Path) -> list[dict]:
    frames = []
    for frame in pinned["frames"]:
        repo, sha = frame["repo"], frame["pinned_commit"]
        limit = pinned["enumeration"]["limits"][repo]
        if frame["role"] == "self":
            cwd, rev = REPO, sha
        else:
            print(f"  fetching {repo} at {sha[:8]} ...", file=sys.stderr)
            cwd = fetch_pinned(REMOTES[repo], sha, workdir / repo.replace("/", "_"))
            rev = sha
        changes = walk(cwd, rev, frame["unit"], frame["source_glob"], limit)
        frames.append({**frame, "changes": changes})
    return frames


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="diff against the pinned copy")
    ap.add_argument("--write", action="store_true", help="overwrite the pinned copy")
    args = ap.parse_args()
    if args.check == args.write:
        ap.error("pass exactly one of --check / --write")

    pinned = json.loads(CORPUS.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="reach-corpus-") as tmp:
        frames = rebuild(pinned, Path(tmp))

    totals = {
        "frames": len(frames),
        "changes": sum(len(f["changes"]) for f in frames),
        "added_source_lines": sum(
            c["added_source_lines"] for f in frames for c in f["changes"]
        ),
    }

    if args.write:
        CORPUS.write_text(
            json.dumps({**pinned, "totals": totals, "frames": frames}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {CORPUS.relative_to(REPO)}: {totals}")
        return 0

    drift = []
    if totals != pinned["totals"]:
        drift.append(f"totals: pinned {pinned['totals']} != rebuilt {totals}")
    for old, new in zip(pinned["frames"], frames, strict=True):
        o = [(c["commit"], c["added_source_lines"]) for c in old["changes"]]
        n = [(c["commit"], c["added_source_lines"]) for c in new["changes"]]
        if o == n:
            continue
        where = next(
            (i for i in range(max(len(o), len(n))) if o[i : i + 1] != n[i : i + 1]),
            None,
        )
        drift.append(
            f"{old['repo']}: {len(o)} pinned changes != {len(n)} rebuilt, "
            f"first difference at index {where}"
        )
    if drift:
        print("CORPUS DRIFT", *drift, sep="\n  ")
        return 1
    print(f"corpus reproduces: {totals}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
