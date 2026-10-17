"""The repository's test baseline, read before any work is proposed.

One run of the repository's own suite splits its tests into the ones already
failing (``red``) and the ones already passing (``green``). A
:class:`BaselineObservation` keeps that split together with the argv it came
from, and derives the commands an evidence-derived contract needs: a
demonstration re-runs one red test, and acceptance re-runs the suite with the red
tests deselected, so a green result means the work broke nothing that was
already working.

Where the runner comes from is read off repository declarations only —
``pyproject.toml``, ``package.json``, ``Cargo.toml``, ``go.mod`` — and only
pytest output is parsed, because the ``-rA`` summary is what makes a per-test
split available at all.
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

# Observing runs the suite once over the whole repository, so it is given the
# same wall-clock budget as a checker invocation: a run past it is an environment
# fault rather than something to report as a finding.
OBSERVE_TIMEOUT_S = TYPECHECK_TIMEOUT_S

# The summary lines ``pytest -rA`` prints per test: ``FAILED id - reason``,
# ``ERROR id - reason``, ``PASSED id - reason``. The reason tail is optional, so
# the id is everything up to it.
_FAILED = re.compile(r"^(?:FAILED|ERROR)\s+(?P<id>[^\n]+?)(?:\s+-\s+.*)?$")
_PASSED = re.compile(r"^PASSED\s+(?P<id>[^\n]+?)(?:\s+-\s+.*)?$")


@dataclass(frozen=True)
class BaselineObservation:
    """What one run of the repository's suite said about it.

    The runner is kept beside the split so the same command can be replayed
    later for a single test or for the rest of the suite, instead of a command
    being reconstructed from prose.
    """

    runner: tuple[str, ...]
    """The suite command as argv, e.g. ``("uv", "run", "pytest")``."""

    red: tuple[str, ...] = ()
    """Test ids that failed at baseline."""

    green: tuple[str, ...] = ()
    """Test ids that passed at baseline."""

    @property
    def command(self) -> str:
        """The runner as one shell-quoted command, the form a contract states it in."""
        return shlex.join(self.runner)

    def demonstrations(self) -> tuple[str, ...]:
        """One command per red test that re-runs just that test.

        Empty for a runner whose ids were never observed: only pytest was parsed,
        and appending a node id to the runner is what makes one test selectable.
        """
        if not _is_pytest(self.runner):
            return ()
        return tuple(shlex.join((*self.runner, test_id)) for test_id in self.red)

    def acceptance(self) -> tuple[str, ...]:
        """The commands that should pass once the work is done, read off the split.

        The whole suite when nothing was red. When something was, the suite with
        each red test deselected — acceptance has to be green at baseline too, so
        the tests already failing cannot be part of it. Empty for a runner other
        than pytest, and when nothing passed at baseline: an entirely red suite
        has no green result to show.
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
    """The suite command this repository declares, or ``None`` when it declares none.

    Python is asked first, then the JavaScript adapter's ``package.json`` script,
    then Cargo, then Go. The answer is argv, so a caller can run or quote it
    without splitting a string again.
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
    """The runner located here plus the red/green split from one run of it.

    ``None`` when the repository declares no runner, which a caller reads as "no
    baseline could be had" rather than as a suite with no tests in it.
    """
    runner = locate_runner(root)
    if runner is None:
        return None
    red, green = observe(root, runner, timeout=timeout)
    return BaselineObservation(runner=runner, red=red, green=green)


def observe(
    root: Path, runner: tuple[str, ...], *, timeout: float = OBSERVE_TIMEOUT_S
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The red and green test ids one run of ``runner`` produces at ``root``.

    Only pytest output is parsed, so any other runner yields two empty tuples
    rather than an invented split.
    """
    if not _is_pytest(runner):
        return (), ()
    return _observe_pytest(root, runner, timeout=timeout)


def _observe_pytest(
    root: Path, runner: tuple[str, ...], *, timeout: float
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Run pytest quietly and read its short summary into sorted red and green ids.

    ``-rA`` gives a summary line for every test, ``-q`` keeps the run down to that
    summary, and ``--tb=no`` keeps tracebacks out of output that is parsed line by
    line. ``PYTEST_ADDOPTS`` is dropped so an inherited option cannot change what
    is being observed, and ``NO_COLOR`` keeps the summary lines matchable.
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
        # A runner that cannot start, or a run past the budget, is an environment
        # fault: report nothing observed rather than a suite that is all red.
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
    """``pytest`` for a Python repo that declares it, under ``uv`` if uv owns it.

    ``None`` when ``pyproject.toml`` is absent, unreadable, or declares no pytest:
    a Python repository without a declared suite is not one that can be observed.
    """
    document = _toml(root / "pyproject.toml")
    if document is None or not _declares_pytest(document):
        return None
    if _uv_manages(root, document):
        return ("uv", "run", "pytest")
    return ("pytest",)


def _declares_pytest(document: dict[str, object]) -> bool:
    """Whether a parsed ``pyproject.toml`` declares pytest, as dependency or config.

    A ``dev`` entry in ``dependency-groups``, the same group under
    ``project.optional-dependencies``, or any ``[tool.pytest...]`` table counts.
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
    """Whether ``uv`` owns this project, which decides how pytest is invoked.

    A ``dependency-groups`` table, a ``[tool.uv]`` table, or a ``uv.lock`` file
    each mean the environment is uv's to build, so ``uv run pytest`` is the
    command that works the way the project intends.
    """
    if "dependency-groups" in document:
        return True
    tool = document.get("tool")
    if isinstance(tool, dict) and "uv" in tool:
        return True
    return (root / "uv.lock").is_file()


def _declares_rust(root: Path) -> bool:
    """Whether ``Cargo.toml`` declares a package, i.e. a crate cargo can test."""
    document = _toml(root / "Cargo.toml")
    return document is not None and isinstance(document.get("package"), dict)


def _toml(path: Path) -> dict[str, object] | None:
    """Parse ``path`` as TOML, or ``None`` when missing, unreadable, or not a table.

    Callers read ``None`` as "nothing declared here", so a malformed file is not
    an error to raise: the repository's own declarations are simply not usable.
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
    """Whether ``runner`` ends in ``pytest``, the only output this module parses."""
    return bool(runner) and runner[-1] == "pytest"
