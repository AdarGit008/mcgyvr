"""The `mcgyvr sandbox` inspection command.

It exists so a stranger can see, before running anything, which mode is in
force and what the sandbox will try to install — the surfacing #29/#30 ask
for. The stack lines are asserted here; the mode line depends on whether the
test machine has Docker and is left to the sandbox suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.cli import main


def test_sandbox_reports_a_detected_stack(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("# lock\n", encoding="utf-8")

    code = main(["sandbox", str(tmp_path)])
    out = capsys.readouterr().out

    assert code == 0
    assert "base image: python:3.12-slim" in out
    assert "pip install uv && uv sync --frozen" in out


def test_sandbox_reports_an_undetected_stack_with_the_override(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "README.md").write_text("# docs\n", encoding="utf-8")

    code = main(["sandbox", str(tmp_path)])
    out = capsys.readouterr().out

    assert code == 0
    assert "Stack not detected" in out
    assert "sandbox.image" in out


def test_sandbox_rejects_a_path_that_is_not_a_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nope"
    code = main(["sandbox", str(missing)])
    assert code == 1
    assert "not a directory" in capsys.readouterr().err
