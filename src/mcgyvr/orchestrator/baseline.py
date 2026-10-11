"""The baseline-observation locator: the test runner a repository declares,
run once to read which tests are red and green before any change.

The decomposer must not let a model invent the command that evidences a change.
A model can name a command it has never run; a repository's own declaration,
run once, can only name what is there. This module is the "read the
declaration, never guess" rule applied to tests — the sibling of
:meth:`~mcgyvr.gate.adapter.LanguageAdapter.locate_type_check_command`, which
applies the same rule to type checkers (#114).

Two halves, in the order they must run:

* **Detection** (:func:`locate_runner`) reads a repository's *declaration* and
  returns the runner, or ``None``. A ``tests/`` directory, a convention, or a
  file name is not a declaration: Python is only detected from ``pyproject.toml``
  (pytest listed in ``[dependency-groups].dev`` — uv's spelling — or in
  ``[project.optional-dependencies].dev``, or ``[tool.pytest.ini_options]``),
  JS/TS from ``package.json``'s ``scripts.test``, Rust from ``Cargo.toml``'s
  ``[package]`` table, Go from ``go.mod``. Where no declaration names a runner,
  the locator declines cleanly rather than guessing.
* **Observation** (:func:`observe`) runs the detected runner once, in the
  repository, and reads which tests failed (red) and which passed (green) at
  baseline. The run is the smallest meaningful slice of a real answer: pytest's
  own short-summary report, which names each failing and passing test.

:class:`BaselineObservation` carries the two facts back — the runner command and
the red/green split — and turns them into the commands a ``code`` contract
derives: a ``demonstration`` per red test (a command that fails at baseline and
passes after) and one ``acceptance`` naming the passing suite (a command that
passes at baseline and after). Only the pytest runner can name an individual
test today; the other runners are detected, and their observation is left for a
later stage, so nothing here invents per-test facts it has not read.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

from mcgyvr.gate.adapters import JavaScriptAdapter
from mcgyvr.gate.typecheck import TYPECHECK_TIMEOUT_S

#: Wall-clock ceiling for the one observation run, shared with the type-check
#: pass: both are "one checking command may take this long". Reusing the
#: classified number keeps this file free of an unclassified policy number.
OBSERVE_TIMEOUT_S = TYPECHECK_TIMEOUT_S

#: pytest's short-summary lines, one per outcome. The id is everything up to the
#: `` - `` that separates a failing test from its one-line reason.
_FAILED = re.compile(r"^(?:FAILED|ERROR)\s+(?P<id>[^\n]+?)(?:\s+-\s+.*)?$")
_PASSED = re.compile(r"^PASSED\s+(?P<id>[^\n]+?)(?:\s+-\s+.*)?$")


@dataclass(frozen=True)
class BaselineObservation:
    """What the locator read: a declared runner and the baseline red/green split.

    ``red`` and ``green`` are the test ids the runner itself printed — pytest
    node ids such as ``tests/test_demo.py::test_failing``. They are facts read
    from a run, never synthesised, so an empty tuple means *nothing was read*:
    a run that failed to produce a readable report and a suite with no tests of
    that colour are both "nothing to derive".
    """

    runner: tuple[str, ...]
    """The suite command as argv, e.g. ``("uv", "run", "pytest")``."""

    red: tuple[str, ...] = ()
    """Test ids that failed at baseline."""

    green: tuple[str, ...] = ()
    """Test ids that passed at baseline."""

    @property
    def command(self) -> str:
        """The runner, joined the way a contract writes a command."""
        return shlex.join(self.runner)

    def demonstrations(self) -> tuple[str, ...]:
        """A command per red test: the runner naming exactly that failing test.

        Each command must fail at baseline and pass after — the
        ``failing_test_first`` evidence, one per test the change is answerable
        for. Only a runner whose syntax can name one test yields anything here;
        the others return ``()`` so the model's own demonstration (or none)
        remains the only path rather than a fabricated one.
        """
        if not _is_pytest(self.runner):
            return ()
        return tuple(shlex.join((*self.runner, test_id)) for test_id in self.red)

    def acceptance(self) -> tuple[str, ...]:
        """The passing suite as one command; ``()`` when none is green.

        With red tests present the passing suite is the suite with each red
        test deselected — the same tests the worker's change must not break.
        With none red the whole suite is the passing suite. Both pass at
        baseline and after, which is what ``tests_pass`` means.
        """
        if not _is_pytest(self.runner):
            return ()
        if not self.green:
            return ()
        if not self.red:
            return (self.command,)
        deselected = [f"--deselect={test_id}" for test_id in self.red]
        return (shlex.join((*self.runner, *deselected)),)


def locate_runner(root: Path) -> tuple[str, ...] | None:
    """The test runner ``root`` declares, or ``None`` — read, never guessed.

    Detection reads only the files a repository uses to state its test tooling;
    a ``tests/`` directory or a file name is not a declaration. The order is the
    brief's own — Python, JS/TS, Rust, Go — and a repository that carries two
    declarations is answered by the first, on the same "the contract always
    wins" principle that governs every sniff here.
    """
    python = _python_runner(root)
    if python is not None:
        return python
    js = JavaScriptAdapter().locate_test_command(root)
    if js is not None:
        return tuple(js)
    if _declares_rust(root):
        return ("cargo", "test")
    if (root / "go.mod").is_file():
        return ("go", "test", "./...")
    return None


def locate_baseline(
    root: Path, *, timeout: float = OBSERVE_TIMEOUT_S
) -> BaselineObservation | None:
    """Detect the runner and read the baseline red/green split, or decline.

    ``None`` is an ordinary answer meaning *this repository declares no test
    runner* — the decomposer then derives nothing from a run, and a proposal's
    own ``demonstration``/``acceptance`` fields (or the gate alone) stand. It is
    load-bearing rather than a shrug: where it is returned, no command is
    fabricated for this repository.
    """
    runner = locate_runner(root)
    if runner is None:
        return None
    red, green = observe(root, runner, timeout=timeout)
    return BaselineObservation(runner=runner, red=red, green=green)


def observe(
    root: Path, runner: tuple[str, ...], *, timeout: float = OBSERVE_TIMEOUT_S
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Run ``runner`` once in ``root``; return ``(red, green)`` test ids.

    Only the pytest runner has a stable per-test report to read today. The other
    runners are not run here: their test output is framework-specific, and
    running an arbitrary ``npm test`` inside decomposition is a side effect this
    stage will not take. Returning two empty tuples is the honest answer — *no
    facts were read* — and the decomposer treats it as nothing to derive.
    """
    if not _is_pytest(runner):
        return (), ()
    return _observe_pytest(root, runner, timeout=timeout)


def _observe_pytest(
    root: Path, runner: tuple[str, ...], *, timeout: float
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """One pytest run; its short summary is the whole answer.

    ``-rA`` asks pytest to report every outcome, not only failures, so one run
    yields both the red and the green split. ``--tb=no`` keeps the tracebacks
    out — they are not the fact being read, and a failing test's one-line reason
    is enough for a demonstration. Colour is forced off and the ambient
    ``PYTEST_ADDOPTS`` is dropped so the operator's shell cannot change the
    report's shape under this reader.
    """
    argv = [*runner, "-q", "-rA", "--tb=no"]
    env = {key: value for key, value in os.environ.items() if key != "PYTEST_ADDOPTS"}
    env["NO_COLOR"] = "1"
    try:
        proc = subprocess.run(
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        # The runner is not there to run, or did not finish in budget. That is a
        # fact about the environment, not about the tests: no facts were read.
        return (), ()

    red: list[str] = []
    green: list[str] = []
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        failed = _FAILED.match(stripped)
        if failed is not None:
            red.append(failed.group("id").strip())
            continue
        passed = _PASSED.match(stripped)
        if passed is not None:
            green.append(passed.group("id").strip())
    return tuple(sorted(red)), tuple(sorted(green))


def _python_runner(root: Path) -> tuple[str, ...] | None:
    """pytest, read from ``pyproject.toml`` — and fronted by uv when uv manages."""
    document = _toml(root / "pyproject.toml")
    if document is None or not _declares_pytest(document):
        return None
    if _uv_manages(root, document):
        return ("uv", "run", "pytest")
    return ("pytest",)


def _declares_pytest(document: dict[str, object]) -> bool:
    """pytest listed in a dependency group, or pytest's own config table.

    A dependency is *pytest* when its specifier names pytest — ``pytest``,
    ``pytest>=8``, ``pytest[xdist]`` — and not when it merely contains the
    string (``pytest-asyncio`` names another package). ``[tool.pytest.ini_options]``
    is a declaration on its own: a repository that configures pytest has said it
    runs pytest.
    """
    groups = document.get("dependency-groups")
    if isinstance(groups, dict) and _group_has_pytest(groups.get("dev")):
        return True
    project = document.get("project")
    if isinstance(project, dict):
        optional = project.get("optional-dependencies")
        if isinstance(optional, dict) and _group_has_pytest(optional.get("dev")):
            return True
    tool = document.get("tool")
    return isinstance(tool, dict) and isinstance(tool.get("pytest"), dict)


def _group_has_pytest(entries: object) -> bool:
    if not isinstance(entries, list):
        return False
    return any(
        isinstance(entry, str)
        and re.split(r"[<>=!~\[;@\s]", entry, maxsplit=1)[0] == "pytest"
        for entry in entries
    )


def _uv_manages(root: Path, document: dict[str, object]) -> bool:
    """Whether uv manages this project: its own tables, or its lockfile."""
    if "dependency-groups" in document:
        return True
    tool = document.get("tool")
    if isinstance(tool, dict) and "uv" in tool:
        return True
    return (root / "uv.lock").is_file()


def _declares_rust(root: Path) -> bool:
    """Whether ``Cargo.toml`` carries a ``[package]`` table — parsed, not grepped."""
    document = _toml(root / "Cargo.toml")
    return document is not None and isinstance(document.get("package"), dict)


def _toml(path: Path) -> dict[str, object] | None:
    """``path`` parsed as TOML, or ``None`` when it is not a declaration to read.

    An unreadable or unparseable manifest is not a declaration, and nothing here
    raises: the answer to "does this repository declare a runner" is no, and a
    malformed file is the target's own business.
    """
    if not path.is_file():
        return None
    try:
        with path.open("rb") as handle:
            document = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(document, dict):
        return None
    return document


def _is_pytest(runner: tuple[str, ...]) -> bool:
    """Whether ``runner`` invokes pytest (bare, or through ``uv run``)."""
    return bool(runner) and runner[-1] == "pytest"
