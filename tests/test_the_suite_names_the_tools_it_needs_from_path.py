"""The suite says what it needs from PATH, once, before any test runs.

``tests/conftest.py`` ``pytest_configure`` looks up the programs the tests run
by bare name (:data:`tests._helpers.SUITE_TOOLS`). All found: PATH is left as
it is. One missing: the folder of the interpreter running pytest goes first on
PATH. One missing even then: the run stops with one message that names it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from tests import conftest
from tests._helpers import SUITE_TOOLS, missing_from, with_first

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="the stand-in programs are POSIX executables"
)


def programs(folder: Path, *names: str) -> Path:
    """``folder`` holding an executable file for each of ``names``."""
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        program = folder / name
        program.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        program.chmod(0o755)
    return folder


def test_a_path_with_every_tool_misses_nothing(tmp_path: Path) -> None:
    folder = programs(tmp_path / "bin", *SUITE_TOOLS)
    assert missing_from(str(folder)) == ()


def test_the_tools_a_path_does_not_hold_are_named_in_order(tmp_path: Path) -> None:
    folder = programs(tmp_path / "bin", "ruff")
    assert missing_from(str(folder)) == ("python", "mypy")
    assert missing_from("") == SUITE_TOOLS


def test_a_file_that_is_not_executable_is_not_a_tool(tmp_path: Path) -> None:
    folder = programs(tmp_path / "bin", *SUITE_TOOLS)
    (folder / "python").chmod(0o644)
    assert missing_from(str(folder)) == ("python",)


def test_putting_a_folder_first_twice_puts_it_there_once() -> None:
    path = os.pathsep.join(["/usr/bin", "/bin"])
    once = with_first(path, "/venv/bin")
    assert once == os.pathsep.join(["/venv/bin", "/usr/bin", "/bin"])
    assert with_first(once, "/venv/bin") == once
    assert with_first("", "/venv/bin") == "/venv/bin"


def test_with_every_tool_on_path_the_hook_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pytestconfig: pytest.Config
) -> None:
    path = str(programs(tmp_path / "bin", *SUITE_TOOLS))
    monkeypatch.setenv("PATH", path)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "elsewhere" / "python"))
    before = dict(os.environ)

    conftest.pytest_configure(pytestconfig)

    assert dict(os.environ) == before


def test_a_missing_tool_next_to_the_interpreter_puts_its_folder_first_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pytestconfig: pytest.Config
) -> None:
    venv = programs(tmp_path / "venv" / "bin", *SUITE_TOOLS)
    host = programs(tmp_path / "host", "git")
    monkeypatch.setenv("PATH", str(host))
    monkeypatch.setattr(sys, "executable", str(venv / "python"))

    conftest.pytest_configure(pytestconfig)
    conftest.pytest_configure(pytestconfig)

    assert os.environ["PATH"] == os.pathsep.join([str(venv), str(host)])


def test_a_tool_missing_even_next_to_the_interpreter_stops_the_run_naming_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pytestconfig: pytest.Config
) -> None:
    venv = programs(tmp_path / "venv" / "bin", "python", "ruff")
    monkeypatch.setenv("PATH", str(tmp_path / "host"))
    monkeypatch.setattr(sys, "executable", str(venv / "python"))

    with pytest.raises(pytest.UsageError) as stopped:
        conftest.pytest_configure(pytestconfig)

    message = str(stopped.value)
    assert message.startswith("the tests run mypy by name"), message
    assert "uv run pytest" in message
    assert os.environ["PATH"] == str(tmp_path / "host")
