""

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

#
#
#
OBSERVE_TIMEOUT_S = TYPECHECK_TIMEOUT_S

#
#
_FAILED = re.compile(r"^(?:FAILED|ERROR)\s+(?P<id>[^\n]+?)(?:\s+-\s+.*)?$")
_PASSED = re.compile(r"^PASSED\s+(?P<id>[^\n]+?)(?:\s+-\s+.*)?$")


@dataclass(frozen=True)
class BaselineObservation:
    ""

    runner: tuple[str, ...]
    """The suite command as argv, e.g. ``("uv", "run", "pytest")``."""

    red: tuple[str, ...] = ()
    """Test ids that failed at baseline."""

    green: tuple[str, ...] = ()
    """Test ids that passed at baseline."""

    @property
    def command(self) -> str:
        ""
        return shlex.join(self.runner)

    def demonstrations(self) -> tuple[str, ...]:
        ""
        if not _is_pytest(self.runner):
            return ()
        return tuple(shlex.join((*self.runner, test_id)) for test_id in self.red)

    def acceptance(self) -> tuple[str, ...]:
        ""
        if not _is_pytest(self.runner):
            return ()
        if not self.green:
            return ()
        if not self.red:
            return (self.command,)
        deselected = [f"--deselect={test_id}" for test_id in self.red]
        return (shlex.join((*self.runner, *deselected)),)


def locate_runner(root: Path) -> tuple[str, ...] | None:
    ""
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
    ""
    runner = locate_runner(root)
    if runner is None:
        return None
    red, green = observe(root, runner, timeout=timeout)
    return BaselineObservation(runner=runner, red=red, green=green)


def observe(
    root: Path, runner: tuple[str, ...], *, timeout: float = OBSERVE_TIMEOUT_S
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    ""
    if not _is_pytest(runner):
        return (), ()
    return _observe_pytest(root, runner, timeout=timeout)


def _observe_pytest(
    root: Path, runner: tuple[str, ...], *, timeout: float
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    ""
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
        #
        #
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
    ""
    document = _toml(root / "pyproject.toml")
    if document is None or not _declares_pytest(document):
        return None
    if _uv_manages(root, document):
        return ("uv", "run", "pytest")
    return ("pytest",)


def _declares_pytest(document: dict[str, object]) -> bool:
    ""
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
    ""
    if "dependency-groups" in document:
        return True
    tool = document.get("tool")
    if isinstance(tool, dict) and "uv" in tool:
        return True
    return (root / "uv.lock").is_file()


def _declares_rust(root: Path) -> bool:
    ""
    document = _toml(root / "Cargo.toml")
    return document is not None and isinstance(document.get("package"), dict)


def _toml(path: Path) -> dict[str, object] | None:
    ""
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
    ""
    return bool(runner) and runner[-1] == "pytest"
