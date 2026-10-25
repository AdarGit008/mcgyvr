"""A command pytest cannot report for keeps its raw output and its own verdict.

The gate asks for pytest's report only where adding the flags cannot change
what the command means (:func:`mcgyvr.gate.junit.reporting`): pytest, run on
its own, through ``python -m`` or through a project runner, with no ``--``
after which a flag would be read as a file, and no report of the command's own.
Anything else runs exactly as the contract wrote it and keeps the one finding
with the tail of its output. And a command that took the flags but wrote no
report is run again as written, and that run is the one judged — so the flags
can never turn a pass into a failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mcgyvr.gate.acceptance import Acceptance
from mcgyvr.gate.junit import REPORT, reporting
from mcgyvr.sandbox.tempdir import TempDirSandbox
from tests._helpers import git

FLAGS = (f"--junitxml={REPORT}", "-o", "junit_family=xunit1")


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
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


@pytest.mark.parametrize(
    "command",
    [
        ("pytest",),
        ("py.test", "-q", "tests"),
        ("/opt/tools/bin/pytest", "-x"),
        ("python", "-m", "pytest", "tests/test_a.py"),
        ("python3.12", "-m", "pytest"),
        ("uv", "run", "pytest", "-q"),
        ("uv", "run", "--frozen", "python", "-m", "pytest"),
        ("uv", "run", "--python=3.12", "--", "pytest"),
        ("poetry", "run", "pytest"),
    ],
)
def test_pytest_is_asked_for_its_report(command: tuple[str, ...]) -> None:
    assert reporting(command) == (*command, *FLAGS)


@pytest.mark.parametrize(
    "command",
    [
        (),
        ("sh", "-c", "pytest -q"),
        ("make", "test"),
        ("npm", "test"),
        ("python", "-c", "import pytest"),
        ("python", "-m", "unittest"),
        ("pytest", "-q", "--", "tests/test_a.py"),
        ("pytest", "--junitxml=mine.xml"),
        ("pytest", "--junit-xml", "mine.xml"),
        ("pytest", "--junit-prefix=x"),
        ("pytest", "-p", "no:junitxml"),
        ("uv", "run"),
        # An option that may take the next token as its value: that token is
        # not the program, whatever it is called.
        ("uv", "run", "--with", "pytest", "python", "check.py"),
        ("uv", "sync"),
    ],
)
def test_anything_else_runs_as_written(command: tuple[str, ...]) -> None:
    assert reporting(command) is None


def test_a_command_that_is_not_pytest_keeps_the_tail_of_its_output(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path, {})
    command = ("sh", "-c", "echo FAILED tests/test_a.py::test_b; exit 1")
    with TempDirSandbox(repo) as sandbox:
        report = Acceptance(sandbox, (command,)).run()

    (finding,) = report.findings
    assert (finding.code, finding.test_id, finding.names_a_file) == (
        "failed",
        None,
        False,
    )
    # The id is only in what the command printed, so it is quoted, not claimed.
    assert "FAILED tests/test_a.py::test_b" in finding.message


def test_pytest_with_a_report_of_its_own_keeps_the_raw_tail(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {"tests/test_a.py": "def test_b():\n    assert 1 == 2\n"},
    )
    command = (
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "--junitxml=own.xml",
    )
    with TempDirSandbox(repo) as sandbox:
        report = Acceptance(sandbox, (command,)).run()

    (finding,) = report.findings
    assert (finding.code, finding.test_id) == ("failed", None)
    assert "assert 1 == 2" in finding.message


# A pytest that refuses the report flag the way `-p no:junitxml` in a project's
# own options would (a usage error, exit 4), and passes when run as written.
REFUSES_THE_FLAG = """\
#!/usr/bin/env python3
import sys

sys.exit(4 if any(a.startswith("--junitxml") for a in sys.argv) else 0)
"""


def test_a_command_that_wrote_no_report_is_judged_by_its_plain_run(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path, {"bin/pytest": REFUSES_THE_FLAG})
    with TempDirSandbox(repo) as sandbox:
        report = Acceptance(sandbox, (("bin/pytest",),)).run()

    assert report.findings == ()
    assert report.environment_issues == ()
