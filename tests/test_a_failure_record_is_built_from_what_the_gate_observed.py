"""A failure record holds what a check reported as data, and nothing it guessed.

:class:`mcgyvr.notes.FailureNotes` is built after the gate ran, from its
result: each finding's check, path, line and code, and — where the check ran a
command — that command and its exit. Every check here runs for real: ruff and
mypy over a real change set, the acceptance rung over a real sandbox. What is
asserted is the record, field by field, including the fields that must stay
empty because the check only said them in prose.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from mcgyvr.gate.acceptance import Acceptance
from mcgyvr.gate.changeset import ChangeSet
from mcgyvr.gate.findings import Finding
from mcgyvr.gate.runner import Gate, GateResult, InconclusiveRung
from mcgyvr.gate.typecheck import TypeCheck
from mcgyvr.notes import FailureNotes, NoteKind
from mcgyvr.redact import REDACTED
from mcgyvr.sandbox.tempdir import TempDirSandbox


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _repo(tmp_path: Path, **files: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "seed.py").write_text("SEED = 1\n", encoding="utf-8")
    for name, text in files.items():
        (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _record(gate: GateResult) -> FailureNotes:
    record = FailureNotes.of_gate(gate, rung="local_a", family="local", attempt=1)
    assert record is not None, f"the gate accepted the change: {gate}"
    return record


def test_a_lint_finding_gives_check_path_line_and_code(tmp_path: Path) -> None:
    """ruff's own report, as data: the unused import's file, line and code."""
    repo = _repo(tmp_path)
    (repo / "bad.py").write_text("import os\n\nVALUE = undefined_name\n")

    record = _record(Gate().run(ChangeSet.detect(repo)))

    by_code = {note.code: note for note in record.notes}
    unused = by_code["F401"]
    assert (unused.check, unused.kind, unused.path, unused.line) == (
        "lint",
        NoteKind.FINDING,
        "bad.py",
        1,
    )
    undefined = by_code["F821"]
    assert undefined.line == 3
    # ruff names the undefined name only in its sentence, so the record does
    # not claim it as data: a symbol parsed out of prose is a guess.
    assert "undefined_name" in undefined.message
    assert undefined.symbol is None
    assert (unused.command, unused.exit_code, unused.test_id) == (None, None, None)
    assert record.checks == ("lint",)
    assert unused.for_model() == "bad.py:1: lint [F401]: " + unused.message


def test_a_typecheck_finding_gives_its_command_and_exit(tmp_path: Path) -> None:
    """mypy's diagnostic on the worker's line, with the command that found it."""
    repo = _repo(tmp_path, **{"mypy.ini": "[mypy]\n"})
    (repo / "count.py").write_text(
        "def count(rows: list[int]) -> int:\n    return rows\n", encoding="utf-8"
    )

    gate = Gate().run(ChangeSet.detect(repo), typecheck=TypeCheck(repo))

    record = _record(gate)
    (note,) = [n for n in record.notes if n.check == "typecheck"]
    assert (note.path, note.line, note.code) == ("count.py", 2, "return-value")
    assert note.command is not None
    assert shlex.split(note.command)[0] == "mypy"
    assert shlex.split(note.command)[-1] == "count.py"
    assert note.exit_code == 1


def test_an_acceptance_failure_gives_the_command_and_its_exit(tmp_path: Path) -> None:
    """The acceptance rung ran a command: the record carries it and its exit.

    The command is the contract's own, and the file position is not a file, so
    the note names no path — and the worker's line leaves the command out
    (``tests/test_pattern_e_boundaries.py``).
    """
    repo = _repo(tmp_path)
    command = ("sh", "-c", "echo failing; exit 3")
    with TempDirSandbox(repo) as sandbox:
        report = Acceptance(sandbox, (command,)).run()

    record = _record(GateResult(findings=report.findings))

    (note,) = record.notes
    assert (note.check, note.code, note.path) == ("acceptance", "failed", None)
    assert note.command == shlex.join(command)
    assert note.exit_code == 3
    assert note.command not in note.for_model()


def test_an_undecided_rung_is_recorded_with_the_tools_exit() -> None:
    """A rung that could not decide rejects the change, and says so in the record."""
    gate = GateResult(
        inconclusive=(
            InconclusiveRung(
                adapter="python", rung="lint", tool="ruff", exit_code=2, detail="boom"
            ),
        )
    )

    (note,) = _record(gate).notes

    assert (note.check, note.kind, note.exit_code) == ("lint", NoteKind.INCONCLUSIVE, 2)
    assert "inconclusive" in note.message


def test_a_message_is_scrubbed_and_a_host_path_is_never_named() -> None:
    """A credential in a check's sentence is redacted; an absolute path is dropped."""
    gate = GateResult(
        findings=(
            Finding(
                check="acceptance",
                path="/abs/where/the/sandbox/was.py",
                line=4,
                message="fetch https://user:hunter2@example.invalid/x failed",
            ),
        )
    )

    (note,) = _record(gate).notes

    assert "hunter2" not in note.message
    assert REDACTED in note.message
    assert note.path is None


def test_an_accepted_change_leaves_no_record(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "good.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n")

    gate = Gate().run(ChangeSet.detect(repo))

    assert gate.accepted
    assert FailureNotes.of_gate(gate, rung="r", family="local", attempt=1) is None
