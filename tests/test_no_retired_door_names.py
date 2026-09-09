"""No file a reader would follow names the retired door or its seams.

``tools/runs/run.sh`` was archived on 2026-09-05 (``archive/runs/run.sh``)
when ``python -m mcgyvr.serving.run`` became the one access point to the rigs,
and the three variables that let a caller stand a substitute behind a reading
— ``RUN_DOCKER``, ``RUN_SSH``, ``RUN_RIG_SNAPSHOT_CMD`` — left the door's
vocabulary with it: a step reaches a rig only through the ``ssh`` and
``docker`` the door puts first on PATH. ``mcgyvr/serving.py`` is the file a
reader guesses the door lives in and finds nothing under. A mention of any of
these in code or prose under ``src/``, ``tools/`` or ``tests/``, or in a file
at the repo root, is a pointer at a door that is not there, and the old name
lingering in a usage line is exactly how an operator comes to type it.

History is exempt because it says what was: ``archive/``, ``records/`` and
``okf/`` are read as records, ``tools/bench/rounds.json`` names what each
round ran through, and a mention of the archived path itself
(``archive/runs/run.sh``) points at history and is admitted. This file is
exempt because it has to spell what it forbids, and so are the two tests that
assert the seams are gone.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: Walked recursively, relative to the repo root.
ROOTS: tuple[str, ...] = ("src", "tools", "tests")

#: The repo root's own files (Makefile, pyproject.toml, ...), not its subtrees.
ROOT_FILES = True

#: Never scanned: history, and the files that spell the names on purpose.
EXEMPT: tuple[str, ...] = (
    "archive",
    "okf",
    "records",
    "tools/bench/rounds.json",
    "tests/test_no_retired_door_names.py",
    # Spells the seam names as the patterns it scans for.
    "tests/test_one_door.py",
    # Asserts RUN_DOCKER is gone from the door's vocabulary and reaches no gate.
    "tests/test_serving_door_cli.py",
)

#: Directories that are not this repository's text.
NOT_SCANNED = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}

#: The names, and what counts as a mention. ``run.sh`` is a word — preceded by
#: nothing, a separator or a slash and never by a letter or a dot — so both
#: ``tools/runs/run.sh`` and a bare ``run.sh`` count and ``dry-run.shell``
#: does not; ``archive/runs/run.sh`` is the archived file's own path and is
#: not a mention of a door that is not there. A line is reported once, under
#: the first name that matches.
RETIRED: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("tools/runs/run.sh", re.compile(r"tools/runs/run\.sh")),
    ("run.sh", re.compile(r"(?<![\w.])(?<!archive/runs/)run\.sh(?!\w)")),
    ("mcgyvr/serving.py", re.compile(r"mcgyvr/serving\.py")),
    ("RUN_DOCKER", re.compile(r"\bRUN_DOCKER\b")),
    ("RUN_SSH", re.compile(r"\bRUN_SSH\b")),
    ("RUN_RIG_SNAPSHOT_CMD", re.compile(r"\bRUN_RIG_SNAPSHOT_CMD\b")),
)


def _files(repo: Path, roots: Iterable[str], *, root_files: bool) -> Iterator[Path]:
    if root_files:
        yield from sorted(p for p in repo.iterdir() if p.is_file())
    for root in roots:
        top = repo / root
        if top.is_file():
            yield top
            continue
        for path in sorted(top.rglob("*")):
            if not path.is_file():
                continue
            if NOT_SCANNED & set(path.relative_to(repo).parts):
                continue
            yield path


def _exempt(rel: str) -> bool:
    return any(rel == e or rel.startswith(e + "/") for e in EXEMPT)


def offenders(
    repo: Path, roots: Iterable[str] = ROOTS, *, root_files: bool = ROOT_FILES
) -> list[str]:
    """Every ``path:line: NAME`` under ``roots`` where a retired name appears."""
    hits: list[str] = []
    for path in _files(repo, roots, root_files=root_files):
        rel = path.relative_to(repo).as_posix()
        if _exempt(rel):
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


def test_no_retired_door_name_under_src_tools_tests_or_at_the_root() -> None:
    hits = offenders(REPO)
    assert not hits, (
        f"{len(hits)} mention(s) of a retired door name, each path:line: name. "
        "The fix is the door command (python -m mcgyvr.serving.run --host H "
        "--campaign C --step PATH --model M) or the gate script that owns the "
        f"rule (02-rig.py, 04-workload.py, 07-teardown.py, 08-parse.py): {hits}"
    )


def test_the_scan_can_fail(tmp_path: Path) -> None:
    """The canary: a tree that mentions every name is caught, once per line,
    the exempt history is not, and naming the archive's own path is not a
    mention."""
    (tmp_path / "tools" / "runs").mkdir(parents=True)
    (tmp_path / "tools" / "runs" / "note.txt").write_text(
        "start me through tools/runs/run.sh\n"
        "or run.sh for short\n"
        "the door in mcgyvr/serving.py\n"
        "a dry-run.shell is not a mention\n"
        "ported from archive/runs/run.sh, which is history\n",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "door.py").write_text(
        "SEAM = os.environ.get('RUN_SSH')\n", encoding="utf-8"
    )
    (tmp_path / "Makefile").write_text(
        "export RUN_DOCKER=docker RUN_SSH=ssh\nRUN_RIG_SNAPSHOT_CMD=cat\n",
        encoding="utf-8",
    )
    (tmp_path / "archive").mkdir()
    (tmp_path / "archive" / "old.md").write_text(
        "tools/runs/run.sh\n", encoding="utf-8"
    )
    assert offenders(tmp_path) == [
        "Makefile:1: RUN_DOCKER",
        "Makefile:2: RUN_RIG_SNAPSHOT_CMD",
        "src/door.py:1: RUN_SSH",
        "tools/runs/note.txt:1: tools/runs/run.sh",
        "tools/runs/note.txt:2: run.sh",
        "tools/runs/note.txt:3: mcgyvr/serving.py",
    ]
