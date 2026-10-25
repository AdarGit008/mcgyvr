"""Failing tests come first in a record, and a long red suite stays bounded.

One note per failing test makes the number of notes follow the suite, so the
acceptance rung notes at most :data:`mcgyvr.gate.acceptance.MAX_TESTS_NOTED`
tests one by one and counts the rest, one note per command — one note fewer
than a worker is shown in full (:data:`mcgyvr.worker.prompt.MAX_NOTES_SHOWN`),
so the count is shown too. A rewrite or a timeout, which reject the change
whatever the tests say, comes first; then the tests a report named; then the
raw output of the other failing commands, wherever they ran.
"""

from __future__ import annotations

from pathlib import Path

from mcgyvr.gate.acceptance import MAX_TESTS_NOTED, Acceptance
from mcgyvr.gate.runner import GateResult
from mcgyvr.notes import FailureNotes
from mcgyvr.sandbox.tempdir import TempDirSandbox
from mcgyvr.worker.prompt import MAX_NOTES_SHOWN, render_notes
from tests._helpers import git

FAILING = 25

CASE = (
    '<testcase classname="tests.test_many" name="test_{n}" '
    'file="tests/test_many.py" line="{line}"><failure message="assert {n} == 0">'
    "E   assert {n} == 0</failure></testcase>"
)
REPORT = (
    '<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">'
    + "".join(CASE.format(n=n, line=3 * n) for n in range(FAILING))
    + "</testsuite></testsuites>"
)

STAND_IN = """\
#!/usr/bin/env python3
import sys
from pathlib import Path

for arg in sys.argv[1:]:
    if arg.startswith("--junitxml="):
        Path(arg.split("=", 1)[1]).write_text(Path("report.xml").read_text())
sys.exit(1)
"""


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    files = {
        "bin/pytest": STAND_IN,
        "report.xml": REPORT,
        "tests/test_many.py": "# stands in for the suite\n",
    }
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (repo / "bin/pytest").chmod(0o755)
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


def test_tests_come_before_raw_output_and_the_rest_are_counted(
    tmp_path: Path,
) -> None:
    raw = ("sh", "-c", "echo RAW TAIL; exit 1")
    with TempDirSandbox(_repo(tmp_path)) as sandbox:
        # The raw command runs first; its note still comes after the tests.
        report = Acceptance(sandbox, (raw, ("bin/pytest",))).run()

    notes = report.findings
    assert len(notes) == MAX_TESTS_NOTED + 2  # the tests, the count, the raw tail
    tests, counted, last = (
        notes[:MAX_TESTS_NOTED],
        notes[MAX_TESTS_NOTED],
        notes[-1],
    )
    assert [n.test_id for n in tests] == [
        f"tests/test_many.py::test_{n}" for n in range(MAX_TESTS_NOTED)
    ]
    assert counted.test_id is None
    assert f"{FAILING - MAX_TESTS_NOTED} more failing tests" in counted.message
    assert counted.command == "bin/pytest"
    assert "RAW TAIL" in last.message

    record = FailureNotes.of_gate(
        GateResult(findings=notes), rung="local_a", family="local", attempt=1
    )
    assert record is not None
    shown = render_notes((record,))
    assert shown is not None
    assert "tests/test_many.py::test_0" in shown
    assert f"{FAILING - MAX_TESTS_NOTED} more failing tests" in shown
    assert "RAW TAIL" not in shown  # past the bound a worker is shown in full
    assert "bin/pytest" not in shown  # nor is the command, ever
    assert MAX_TESTS_NOTED < MAX_NOTES_SHOWN


def test_a_command_killed_at_the_limit_comes_before_the_tests(
    tmp_path: Path,
) -> None:
    hangs = ("sh", "-c", "sleep 30")
    with TempDirSandbox(_repo(tmp_path)) as sandbox:
        report = Acceptance(sandbox, (("bin/pytest",), hangs), timeout=2).run()

    first, *rest = report.findings
    assert (first.code, first.test_id) == ("timeout", None)
    assert [n.test_id for n in rest[:2]] == [
        "tests/test_many.py::test_0",
        "tests/test_many.py::test_1",
    ]
