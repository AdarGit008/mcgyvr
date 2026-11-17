"""A setup that said no to ruff skips only lint, format and the repair.

Setup's ruff question writes ``gate.ruff``. ``false`` leaves the Python
adapter's lint and format rungs out and switches the repair off, since the
repair is ruff's fixes and formatter. Everything else in the gate still judges:
a file that does not parse and a type the declared checker rejects are refused
exactly as with the key unset, and ``gate.enabled`` is untouched.

Every case goes through the driver's own gate call with a setup parsed from
text, as ``param_mutation``'s test does, so what is held is the path from the
policy file to the rung.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from mcgyvr.config import Config, parse, stages
from mcgyvr.contract import loads
from mcgyvr.gate import GateResult

TARGET = "src/pkg/fetch.py"

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

#: An invented unit: nothing is dispatched, the gate only needs a setup to read.
FLEET = """\
units:
  cheap:
    address: http://127.0.0.1:9
    model: any-model
"""

CONTRACT = """
id: write-fetch
task_type: code
task: Write fetch.
interface: fetch(url) returns the url.
target: src/pkg/fetch.py
stop_conditions:
  - The url cannot be read.
type_check: true
acceptance: ["true"]
scope:
  allow: ["src/**"]
"""

#: Parses, types and formats clean; ruff's E711 is its one fault.
LINT_ONLY = (
    "def fetch(url: str) -> str:\n"
    "    if url == None:\n"
    '        return ""\n'
    "    return url\n"
)
#: Parses, types and lints clean; the formatter would reflow its one line.
FORMAT_ONLY = "def fetch(url: str) -> str:\n    return(url)\n"
#: Does not parse.
SYNTAX = "def fetch(url: str) -> str\n    return url\n"
#: Annotated and wrong: ``url`` is declared ``int`` and returned as ``str``.
WRONG_TYPE = "def fetch(url: int) -> str:\n    return url\n"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_IDENTITY},
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository that declares mypy, whose committed target is a placeholder,
    so every line the worker writes is an added line the gate judges."""
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / TARGET).write_text("def placeholder():\n    return None\n", "utf-8")
    (root / "pyproject.toml").write_text(
        '[tool.mypy]\npython_version = "3.12"\n', encoding="utf-8"
    )
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _setup(ruff: bool | None) -> Config:
    policy = "ladder: [cheap]\n"
    if ruff is not None:
        policy += f"gate:\n  ruff: {str(ruff).lower()}\n"
    return parse(FLEET, policy)


def _judged(repo: Path, source: str, ruff: bool | None) -> GateResult:
    from mcgyvr.drive import gate_in_sandbox
    from mcgyvr.sandbox.tempdir import TempDirSandbox

    with TempDirSandbox(repo) as sandbox:
        return gate_in_sandbox(loads(CONTRACT), sandbox, source, config=_setup(ruff))


def _checks(result: GateResult) -> set[str]:
    return {finding.check for finding in result.findings}


@pytest.mark.parametrize(
    ("source", "rung"), [(LINT_ONLY, "lint"), (FORMAT_ONLY, "format")]
)
def test_a_lint_or_format_fault_is_refused_with_the_key_unset_or_on(
    repo: Path, source: str, rung: str
) -> None:
    """The fixtures are real faults: unset (as main) and on both refuse them."""
    for ruff in (None, True):
        result = _judged(repo, source, ruff)
        assert not result.accepted, f"gate.ruff={ruff} accepted a {rung} fault"
        assert rung in _checks(result), result.findings


@pytest.mark.parametrize(
    ("source", "rung"), [(LINT_ONLY, "lint"), (FORMAT_ONLY, "format")]
)
def test_after_no_a_lint_or_format_fault_is_not_judged(
    repo: Path, source: str, rung: str
) -> None:
    result = _judged(repo, source, False)

    assert result.accepted, (
        f"gate.ruff is false and the {rung} rung still refused: {result.findings}"
    )
    assert rung not in _checks(result), result.findings


@pytest.mark.parametrize(
    ("source", "fault"), [(SYNTAX, "syntax"), (WRONG_TYPE, "type")]
)
def test_after_no_a_syntax_or_type_fault_is_still_refused(
    repo: Path, source: str, fault: str
) -> None:
    result = _judged(repo, source, False)

    assert not result.accepted, (
        f"gate.ruff is false and a {fault} fault was accepted: the rest of the "
        "gate must judge as before"
    )
    assert "lint" not in _checks(result) and "format" not in _checks(result)


def test_after_no_the_gate_stays_on_and_only_the_repair_is_off() -> None:
    off = stages(_setup(False))
    unset = stages(_setup(None))

    assert unset["gate"] and unset["repair"], unset
    assert off["gate"], "gate.ruff false turned the whole gate off"
    assert not off["repair"], "the repair is ruff's; gate.ruff false must stop it"
    assert {k: v for k, v in off.items() if k != "repair"} == {
        k: v for k, v in unset.items() if k != "repair"
    }


def test_after_no_the_run_says_lint_and_format_were_not_judged() -> None:
    """One note under `gate.ruff: false`; unset and on say what main says."""
    from mcgyvr.drive import ungated_notes

    (said,) = ungated_notes(_setup(False))
    assert said.startswith("python: lint and format not judged")
    assert "gate.ruff is false" in said
    assert ungated_notes(_setup(None)) == ()
    assert ungated_notes(_setup(True)) == ()
    assert ungated_notes(None) == ()


def test_with_the_gate_off_only_the_ungated_note_is_said() -> None:
    """`gate.enabled: false` already says no language check judged the change."""
    from mcgyvr.drive import ungated_notes

    both = parse(FLEET, "ladder: [cheap]\ngate:\n  enabled: false\n  ruff: false\n")
    (said,) = ungated_notes(both)
    assert said.startswith("ungated:")
