"""A ``tasks_admitted`` row becomes a task: the parent tree on disk, the spec beside it.

#365 flips the tables — real commits from Adar's own repositories are the tasks
the orchestrator is run against, and the owner's admission rule is the view
``tasks_admitted`` in ``~/claude/session-mine/sessions.sqlite`` (657 rows, 475
with an issue body as spec, on 2026-08-25). The corpus lives outside every repo
on purpose: nothing here is a fixture, nothing here is checked in, and this
module opens the database read-only.

**The defect this module prevents is leakage.** A row names the *child* commit
— the one that carries the code and the test — but the task is its *parent*:
the tree as it stood before the work, with the child's test absent, because
that test is the acceptance and not the base. Checking out the child sha would
hand the pool the answer in its own working tree, and every acceptance figure
downstream would be a figure about nothing. So :func:`checkout` takes the first
parent, and only the first parent (the view excludes merges; a second parent is
never the base), and the test that turns this module green asserts the child's
test is not on disk.

**Two refusals are ours, not git's.** A parent sha that the canonical clone
cannot see — the view admits recovered commits (``reachable=0``) whose objects
were found in the store but belong to no ref, and clones move — is checked with
``git cat-file -e <sha>^{commit}`` *before* ``git worktree add`` runs, so the
exception names the sha, the clone, and the child it was the base of, rather
than surfacing git's ``fatal: invalid reference``. A root commit (the view
holds two) has no base tree and is refused at :meth:`Task.from_row`, again by
sha. A finding is a check (ADR-0037): each refusal is a named exception with
the offending thing in its message.

The judge's reference is the issue body (owner decision on #365: output versus
issue body, blind), so ``spec`` is the issue text and ``pr_spec`` is carried
separately and never substituted for it. :func:`iter_tasks` yields the rows
with a spec by default; a task with none is loadable by sha but is not a
mission.
"""

from __future__ import annotations

import sqlite3
import subprocess
from collections.abc import Iterator, Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The corpus. Outside every repo by design (session-mine's README states why).
DEFAULT_DB = Path.home() / "claude" / "session-mine" / "sessions.sqlite"

#: The owner's admission rule, as a view name. Its WHERE clause is the rule;
#: this module does not restate it.
VIEW = "tasks_admitted"


class TaskError(Exception):
    """A row, a parent, or a destination this module refuses, named."""


@dataclass(frozen=True)
class Task:
    """One admitted commit, read as a mission.

    ``sha`` is the child (the commit that landed the work); ``parent`` is the
    base tree the attempt runs in; ``spec`` is the issue body the judge reads;
    ``test_paths`` are the child's test files, relative to ``repo_root``.
    """

    sha: str
    repo_root: Path
    parent: str
    spec: str
    test_paths: tuple[str, ...]
    subject: str = ""
    ts: str = ""
    n_files: int = 0
    issue_numbers: tuple[int, ...] = ()
    pr_numbers: tuple[int, ...] = ()
    pr_spec: str = ""
    reachable: bool = True

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Task:
        """Build a task from one ``tasks_admitted`` row (a dict or sqlite3.Row).

        ``Any`` because sqlite hands back untyped cells; every field is coerced
        here and nowhere else. Required columns: ``sha``, ``repo_root``,
        ``parents``, ``test_paths``. Everything else defaults.
        """
        for column in ("sha", "repo_root", "parents", "test_paths"):
            if column not in row:
                raise TaskError(
                    f"row {_name(row)} has no {column!r} column; a {VIEW} row "
                    "carries it, so this is not one"
                )
        sha = str(row["sha"])
        parents = str(row["parents"] or "").split()
        if not parents:
            raise TaskError(
                f"commit {sha} has no parent (a root commit): there is no base "
                "tree to attempt against, so it is not a task"
            )
        test_paths = tuple(
            line.strip()
            for line in str(row["test_paths"] or "").splitlines()
            if line.strip()
        )
        if not test_paths:
            raise TaskError(
                f"commit {sha} names no test paths: without an acceptance there "
                "is nothing for the gate to run"
            )
        return cls(
            sha=sha,
            repo_root=Path(str(row["repo_root"])),
            parent=parents[0],
            spec=str(row.get("spec") or ""),
            test_paths=test_paths,
            subject=str(row.get("subject") or ""),
            ts=str(row.get("ts") or ""),
            n_files=int(row.get("n_files") or 0),
            issue_numbers=_numbers(row.get("issue_numbers")),
            pr_numbers=_numbers(row.get("pr_numbers")),
            pr_spec=str(row.get("pr_spec") or ""),
            reachable=bool(row.get("reachable", 1)),
        )

    @property
    def has_spec(self) -> bool:
        """Whether the judge has an issue body to read."""
        return bool(self.spec.strip())


def _name(row: Mapping[str, Any]) -> str:
    sha = row.get("sha")
    return f"for {sha}" if sha else "with keys " + ", ".join(sorted(row))


def _numbers(cell: object) -> tuple[int, ...]:
    """``group_concat`` of integers (``'21,22'``) to a tuple; NULL is empty."""
    if cell is None or cell == "":
        return ()
    return tuple(int(part) for part in str(cell).split(",") if part.strip())


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )


def checkout(task: Task, into: Path) -> Path:
    """A detached worktree of the canonical clone at the task's parent sha.

    Refuses, by name, a clone that is not one, a destination that already
    exists, and a parent the clone cannot see — the last one before git is
    asked to add anything, so the message is ours. Returns ``into``.
    """
    root = task.repo_root
    if not root.is_dir():
        raise TaskError(
            f"repo_root {root} for commit {task.sha} is not a directory; the "
            "canonical clone has moved or was never here"
        )
    probe = _git(root, "rev-parse", "--git-dir")
    if probe.returncode != 0:
        raise TaskError(
            f"repo_root {root} for commit {task.sha} is not a git repository: "
            f"{probe.stderr.strip()}"
        )
    if into.exists():
        raise TaskError(
            f"{into} already exists; a worktree for commit {task.sha} goes into "
            "a path nothing else owns"
        )
    seen = _git(root, "cat-file", "-e", f"{task.parent}^{{commit}}")
    if seen.returncode != 0:
        raise TaskError(
            f"parent {task.parent} of commit {task.sha} is not a commit the "
            f"clone at {root} can see; the base tree cannot be checked out "
            f"(reachable={int(task.reachable)} in the view)"
        )
    added = _git(root, "worktree", "add", "--detach", str(into), task.parent)
    if added.returncode != 0:
        raise TaskError(
            f"git worktree add for parent {task.parent} of commit {task.sha} "
            f"into {into} failed: {added.stderr.strip()}"
        )
    return into


def release(worktree: Path) -> None:
    """Remove a worktree :func:`checkout` made, and its registration in the clone.

    A worktree left behind is a directory the canonical clone still lists;
    the next checkout into the same path would then be refused for the wrong
    reason.
    """
    removed = _git(worktree, "worktree", "remove", "--force", str(worktree))
    if removed.returncode != 0:
        raise TaskError(
            f"git worktree remove of {worktree} failed: {removed.stderr.strip()}"
        )


def _connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.is_file():
        raise TaskError(
            f"corpus {db_path} does not exist; the tasks live in "
            "session-mine's sessions.sqlite, outside every repo"
        )
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _as_mapping(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}  # noqa: SIM118 — Row is not a Mapping


def load(db_path: Path, sha: str) -> Task:
    """The task for one child sha, exact match, from the admitted view."""
    with closing(_connect(db_path)) as connection:
        found = connection.execute(
            f"SELECT * FROM {VIEW} WHERE sha = ?", (sha,)
        ).fetchone()
    if found is None:
        raise TaskError(f"commit {sha} is not a row of {VIEW} in {db_path}")
    return Task.from_row(_as_mapping(found))


def iter_tasks(db_path: Path, *, with_spec_only: bool = True) -> Iterator[Task]:
    """Every admitted task, oldest first; by default only those with a spec.

    Root commits are left out in SQL rather than refused one by one: the view
    admits them and :meth:`Task.from_row` would name each, but a loop over
    the corpus is not the place to learn that twice.
    """
    where = "WHERE parents IS NOT NULL AND parents != ''"
    if with_spec_only:
        where += " AND spec IS NOT NULL AND spec != ''"
    with closing(_connect(db_path)) as connection:
        rows = connection.execute(
            f"SELECT * FROM {VIEW} {where} ORDER BY ts, sha"
        ).fetchall()
    for row in rows:
        yield Task.from_row(_as_mapping(row))
