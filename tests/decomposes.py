"""A decomposition handed its checkers instead of finding them on disk."""

from __future__ import annotations

import subprocess
from pathlib import Path

from mcgyvr.orchestrator.decompose import (
    Proposal,
)
from mcgyvr.orchestrator.index import Index, build_index


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def an_annotation(**overrides: object) -> Proposal:
    """A `type_check: true` `code` proposal with no acceptance of its own.

    The empty `acceptance` is the point. `type_check` evidence can only be
    produced by a command, so the decomposer must either locate the repository's
    checker and fill the acceptance in, or refuse when there is none.
    """
    base = {
        "task_type": "code",
        "task": "annotate listing() and its return.",
        "target": "listing.py",
        "stop_conditions": ("the intended element type is ambiguous",),
        "no_semantic_change": True,
        "type_check": True,
    }
    return Proposal(**{**base, **overrides})  # type: ignore[arg-type]


def declaring_mypy(repo: Index) -> Index:
    """The same repository, having declared mypy the way mypy reads it."""
    (repo.root / "pyproject.toml").write_text(
        '[tool.mypy]\nfiles = ["."]\nstrict = true\n'
    )
    git(repo.root, "add", "-A")
    git(repo.root, "commit", "-q", "-m", "declare mypy")
    return build_index(repo.root)
