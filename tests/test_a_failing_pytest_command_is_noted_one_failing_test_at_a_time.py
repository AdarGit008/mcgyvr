"""A failing pytest command is noted one failing test at a time, from its report.

When an acceptance or demonstrating command is pytest, the gate asks it for its
JUnit XML report (:mod:`mcgyvr.gate.junit`) and files one finding — and so one
failure note — per failing test: the test's node id, its file and the line its
definition starts on, the exception pytest recorded, the command as the
contract wrote it, and its exit. Nothing is read out of what the command
printed. The report is the gate's, so it is gone again before the tree is
restored, and no cleanup note names it.

These run the pytest this suite runs under, for real, inside a temp-directory
sandbox; a stand-in ``pytest`` that writes a fixed report pins the reading of
the report on its own, whatever pytest version is installed.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

from mcgyvr.gate.acceptance import Acceptance
from mcgyvr.gate.runner import GateResult
from mcgyvr.notes import FailureNotes, NoteKind
from mcgyvr.sandbox.tempdir import TempDirSandbox
from tests._helpers import git

SUITE = """\
import os

import pytest


def test_passes():
    assert True


def test_compares():
    assert {}.get("a") == "b"


def test_reaches_a_missing_attribute():
    os.not_there


class TestGroup:
    @pytest.mark.parametrize("value", [1, 2])
    def test_value(self, value):
        assert value == 1
"""

PYTEST = (sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider")


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    # A pytest config of its own, so the inner pytest roots at the workspace.
    files = {"pyproject.toml": "[tool.pytest.ini_options]\n", **files}
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if name.startswith("bin/"):
            path.chmod(0o755)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(
        repo,
        "-c",
        "user.email=t@t.invalid",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "-m",
        "base",
    )
    return repo


def _record(findings: GateResult) -> FailureNotes:
    record = FailureNotes.of_gate(findings, rung="local_a", family="local", attempt=1)
    assert record is not None
    return record


def test_each_failing_test_is_its_own_note_with_its_id_file_and_line(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path, {"tests/test_suite.py": SUITE})
    command = (*PYTEST, "tests/test_suite.py")
    with TempDirSandbox(repo) as sandbox:
        report = Acceptance(sandbox, (command,)).run()
        left = sorted(p.name for p in sandbox.workspace.iterdir())

    notes = _record(GateResult(findings=report.findings)).notes

    assert [n.test_id for n in notes] == [
        "tests/test_suite.py::test_compares",
        "tests/test_suite.py::test_reaches_a_missing_attribute",
        "tests/test_suite.py::TestGroup::test_value[2]",
    ]
    assert {(n.check, n.kind, n.code, n.path) for n in notes} == {
        ("acceptance", NoteKind.FINDING, "failed", "tests/test_suite.py")
    }
    # The line each definition starts on: a decorated one starts at its decorator.
    assert [n.line for n in notes] == [10, 14, 19]
    # The command as the contract wrote it (the interpreter's host path is
    # redacted in a note), with none of the gate's report flags.
    assert {n.exit_code for n in notes} == {1}
    (said,) = {n.command for n in notes}
    assert said is not None
    assert said.endswith(shlex.join(command[1:]))
    attribute = notes[1]
    assert "AttributeError: module 'os' has no attribute 'not_there'" in (
        attribute.message
    )
    assert attribute.symbol == "not_there"
    assert [n.symbol for n in (notes[0], notes[2])] == [None, None]
    # The gate's report is not the command's leftover: never noted, never kept.
    assert not any("junit" in note for note in report.notes)
    assert not any("junit" in name for name in left)


def test_a_demonstrating_test_that_still_fails_says_the_defect_is_not_fixed(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path, {"tests/test_suite.py": SUITE})
    command = (*PYTEST, "tests/test_suite.py::test_compares")
    with TempDirSandbox(repo) as sandbox:
        report = Acceptance(sandbox, (), demonstrations=(command,)).run()

    (note,) = _record(GateResult(findings=report.findings)).notes

    assert (note.code, note.test_id) == (
        "demonstration-failed",
        "tests/test_suite.py::test_compares",
    )
    assert "the defect the contract names is not fixed" in note.message


REPORT = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites name="pytest tests"><testsuite name="pytest" errors="1" failures="2"
 skipped="0" tests="4">
<testcase classname="spec.test_stock" name="test_level" file="spec/test_stock.py"
 line="11" time="0.001"><failure message="AssertionError: assert 3 == 4">def \
test_level():
&gt;       assert level() == 4
E       AssertionError: assert 3 == 4

spec/test_stock.py:13: AssertionError</failure></testcase>
<testcase classname="spec.test_stock" name="test_passes" file="spec/test_stock.py"
 line="15" time="0.001"/>
<testcase classname="spec.test_stock.TestShelf" name="test_rows[a-1]"
 file="spec/test_stock.py" line="20" time="0.001"><failure \
message="NameError: name 'shelf_rows' is not defined">E   NameError: name \
'shelf_rows' is not defined</failure></testcase>
<testcase classname="spec.test_stock" name="test_opens" file="spec/test_stock.py"
 line="30" time="0.001"><error message="failed on setup with &quot;OSError: \
gone&quot;">E   OSError: gone</error></testcase>
</testsuite></testsuites>
"""

STAND_IN = """\
#!/usr/bin/env python3
import sys
from pathlib import Path

for arg in sys.argv[1:]:
    if arg.startswith("--junitxml="):
        Path(arg.split("=", 1)[1]).write_text(Path("report.xml").read_text())
print("3 failed")
sys.exit(1)
"""


def test_a_stand_in_pytest_report_is_read_field_by_field(tmp_path: Path) -> None:
    """The report alone decides the notes: three failures, three notes."""
    repo = _repo(
        tmp_path,
        {
            "bin/pytest": STAND_IN,
            "report.xml": REPORT,
            "spec/test_stock.py": "# stands in for the suite\n",
        },
    )
    with TempDirSandbox(repo) as sandbox:
        report = Acceptance(sandbox, (("bin/pytest", "-q"),)).run()

    notes = _record(GateResult(findings=report.findings)).notes

    assert [(n.test_id, n.line, n.code, n.symbol) for n in notes] == [
        ("spec/test_stock.py::test_level", 12, "failed", None),
        (
            "spec/test_stock.py::TestShelf::test_rows[a-1]",
            21,
            "failed",
            "shelf_rows",
        ),
        ("spec/test_stock.py::test_opens", 31, "error", None),
    ]
    assert {(n.path, n.command, n.exit_code) for n in notes} == {
        ("spec/test_stock.py", "bin/pytest -q", 1)
    }
    assert "AssertionError: assert 3 == 4" in notes[0].message
    assert "OSError: gone" in notes[2].message
    # The printed "3 failed" is the command's output, not the report: it is
    # not what a note says.
    assert not any("3 failed" in n.message for n in notes)
