"""No live code or test cites the archived `pending` / `record` modules as live.

``mcgyvr/pending.py`` and ``mcgyvr/record.py`` moved to ``archive/src/mcgyvr/``.
A docstring or comment that cites ``mcgyvr.pending``, ``pending.stash``,
``pending.resume``, "the pending store", or ``record.Attempt`` is a pointer at a
module that is not there. History is exempt (``archive/``, ``records/``,
``okf/``); the fix is to reword the prose to the live ``surrogateescape`` /
``deliver`` convention, never to resurrect the module.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: Walked recursively, relative to the repo root. ``docs/`` is included because
#: ``docs/conflicts.md`` cites the archived ``record.Attempt``.
ROOTS: tuple[str, ...] = ("src", "tests", "docs")

#: Never scanned: history, and this file, which spells the patterns on purpose.
EXEMPT: tuple[str, ...] = ("tests/test_no_stale_pending_citations.py",)

NOT_SCANNED = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}

#: A mention of the archived modules. ``record.Attempt`` is the archived
#: ``record`` module's verdict class, not the live ``records/`` tree.
RETIRED: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("mcgyvr.pending", re.compile(r"mcgyvr\.pending")),
    ("pending.stash", re.compile(r"pending\.stash")),
    ("pending.resume", re.compile(r"pending\.resume")),
    ("pending store", re.compile(r"pending store")),
    ("stash`` was fixed", re.compile(r"stash`` was fixed")),
    ("record.Attempt", re.compile(r"record\.Attempt")),
)


def _files(repo: Path, roots: tuple[str, ...]) -> Iterator[Path]:
    for root in roots:
        top = repo / root
        for path in sorted(top.rglob("*")):
            if not path.is_file():
                continue
            if NOT_SCANNED & set(path.relative_to(repo).parts):
                continue
            yield path


def offenders(repo: Path, roots: tuple[str, ...] = ROOTS) -> list[str]:
    hits: list[str] = []
    for path in _files(repo, roots):
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


def test_no_live_code_cites_the_archived_pending_or_record_modules() -> None:
    hits = offenders(REPO)
    assert not hits, (
        f"{len(hits)} stale citation(s) of the archived pending/record modules, "
        "each path:line: name. Reword to the live surrogateescape/deliver "
        f"convention: {hits}"
    )
