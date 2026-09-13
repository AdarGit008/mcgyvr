"""No live file points at a path that moved into `archive/`.

Several prose, session and README paths moved to ``archive/`` (``docs/archive/
evidence-prose``, ``docs/archive/sessions``, ``tools/*/README.md``,
``forensic-ollama``). A live reference to the old path is a pointer at a file
that is no longer there. History is exempt (``archive/``, ``records/``,
``okf/``); the fix is to repoint the citation at its ``archive/`` path, not to
restore the file.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: Walked recursively, relative to the repo root, plus the repo root's own files
#: (``.gitignore``, ``Makefile``, ...).
ROOTS: tuple[str, ...] = ("src", "tools", "tests")
ROOT_FILES = True

#: Never scanned: history, and this file, which spells the patterns on purpose.
EXEMPT: tuple[str, ...] = ("tests/test_no_live_reference_to_archived_paths.py",)

NOT_SCANNED = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}

#: The old paths, matched by their old spelling so an already-repointed
#: ``archive/...`` citation is not flagged.
RETIRED: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("configs/d7-campaign.json", re.compile(r"configs/d7-campaign\.json")),
    (
        "records/evidence/calibration-2026-08-19/README.md",
        re.compile(r"records/evidence/calibration-2026-08-19/README\.md"),
    ),
    (
        "records/evidence/2026-08-22-coresidency-feasibility/README.md",
        re.compile(r"records/evidence/2026-08-22-coresidency-feasibility/README\.md"),
    ),
    # Anchored on `archive/` so the moved file's own path is not a hit.
    ("tools/problems/README.md", re.compile(r"(?<!archive/)tools/problems/README\.md")),
    (
        "records/sessions/lane/225/2026-08-11-f1-responsiveness-prereg",
        re.compile(r"records/sessions/lane/225/2026-08-11-f1-responsiveness-prereg"),
    ),
    (
        "records/sessions/lane/231/2026-08-13-positive-control-prereg",
        re.compile(r"records/sessions/lane/231/2026-08-13-positive-control-prereg"),
    ),
    # A basename with no root: anchor on the archive path's own prefix, so a
    # repointed citation is not a hit.
    (
        "d7-sleep.aborted-run.README.md",
        re.compile(
            r"(?<!archive/docs/archive/evidence-prose/calibration-2026-08-19/)"
            r"d7-sleep\.aborted-run\.README\.md"
        ),
    ),
)


def _root_files(repo: Path) -> Iterator[Path]:
    """Tracked files directly under the repo root (``.gitignore``, ``Makefile``).

    Enumerated from ``git ls-files`` rather than ``repo.iterdir()`` so an
    untracked worktree artifact (``run.log``, ``run.pid``) is not scanned as if
    it were source.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    for rel in listing.split("\0"):
        if rel and "/" not in rel and (repo / rel).is_file():
            yield repo / rel


def _files(repo: Path, roots: tuple[str, ...], *, root_files: bool) -> Iterator[Path]:
    if root_files:
        yield from sorted(_root_files(repo))
    for root in roots:
        top = repo / root
        for path in sorted(top.rglob("*")):
            if not path.is_file():
                continue
            if NOT_SCANNED & set(path.relative_to(repo).parts):
                continue
            yield path


def offenders(
    repo: Path, roots: tuple[str, ...] = ROOTS, *, root_files: bool = ROOT_FILES
) -> list[str]:
    hits: list[str] = []
    for path in _files(repo, roots, root_files=root_files):
        rel = path.relative_to(repo).as_posix()
        if rel in EXEMPT:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for name, pattern in RETIRED:
                if pattern.search(line):
                    hits.append(f"{rel}:{number}: {name}")
                    break
    return hits


def test_no_live_reference_to_a_path_moved_into_archive() -> None:
    hits = offenders(REPO)
    assert not hits, (
        f"{len(hits)} live reference(s) to paths that moved into archive/, each "
        f"path:line: name. Repoint at the archive/ path: {hits}"
    )
