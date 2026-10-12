"""A line the change rewrote is charged only with the lint the change brought.

The lint rung keeps a diagnostic when its row is one the change added. A
formatter rewrites a line without changing what it says: ``ruff format`` turns
``import os,sys`` into ``import os, sys``, so the line counts as added, and the
four diagnostics on it (E401, I001, F401 twice) were there before the change
and are there after it. Charged to the change, they rejected a ``format`` that
did exactly what the project's own formatter does (e2e run 1, F2), against the
adapter's own promise that a file's pre-existing faults never fail the change.

So the rung also lints the file as it stood at the base and drops an added-line
diagnostic the base already had — matched by ``(code, message)``, one base
diagnostic consumed per match, so a second copy of a fault the base had once is
still the change's. The pair below pins both halves: the reformat is clean, and
a genuinely new fault on the same rewritten line still rejects.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from mcgyvr.gate import Gate
from mcgyvr.gate.adapters import PythonAdapter
from mcgyvr.gate.changeset import ChangeSet

pytestmark = pytest.mark.skipif(shutil.which("ruff") is None, reason="needs ruff")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={
            "PATH": "/usr/bin:/bin",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t.invalid",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        },
    )


def changed(tmp_path: Path, *, base: str, after: str) -> ChangeSet:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "m.py").write_text(base, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    (repo / "m.py").write_text(after, encoding="utf-8")
    return ChangeSet.detect(repo, "HEAD")


def test_the_formatter_output_of_a_faulty_line_is_not_a_lint_rejection(
    tmp_path: Path,
) -> None:
    change = changed(tmp_path, base="import os,sys\n", after="import os, sys\n")
    assert change.files[0].added_lines == {1}, "the reformat rewrote line 1"

    findings = PythonAdapter().lint(change.files, change.repo, base=change.base)

    assert [f for f in findings if f.check == "lint"] == []


def test_the_gate_accepts_the_reformat(tmp_path: Path) -> None:
    """The base reaches the rung through the gate, not only a direct call."""
    change = changed(tmp_path, base="import os,sys\n", after="import os, sys\n")

    result = Gate([PythonAdapter()]).run(change)

    assert not [f for f in result.findings if f.check == "lint"], result.findings


def test_a_new_fault_on_a_rewritten_line_still_rejects(tmp_path: Path) -> None:
    change = changed(tmp_path, base="import os,sys\n", after="import os, sys, json\n")

    result = Gate([PythonAdapter()]).run(change)

    lint = [(f.code, f.message) for f in result.findings if f.check == "lint"]
    assert lint == [("F401", "`json` imported but unused")], lint
    assert not result.accepted


def test_a_second_copy_of_a_pre_existing_fault_is_the_changes(tmp_path: Path) -> None:
    """One base diagnostic excuses one: the multiset, not a set."""
    change = changed(
        tmp_path,
        base="def f():\n    x = 1\n",
        after="def f():\n    x = 1\n\n\ndef g():\n    x = 1\n",
    )

    findings = PythonAdapter().lint(change.files, change.repo, base=change.base)

    assert [(f.code, f.line) for f in findings if f.check == "lint"] == [("F841", 6)]
