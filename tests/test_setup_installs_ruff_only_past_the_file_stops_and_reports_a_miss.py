"""``mcgyvr setup`` installs ruff on the yes, and a miss never ends the run.

The coding branch asks whether ruff runs as the lint/format gate and its
repair; on a yes setup runs ``uv tool install ruff`` after the config is
staged. With no ``uv`` on PATH the install cannot run: setup says so in one
line, as it does for a failed install, and goes on.

The rig is :class:`tests.setup_door.FakeRig` behind the door; the prompts are
answered through the setup's own prompt seams; nothing reaches a machine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr import cli
from mcgyvr.cli.commands.setup import RUFF_QUESTION
from mcgyvr.fleet.roots import data_home
from tests import setup_door as sd

USE_CASE = "Use case — [m] mcgyvr-code, [k] code, [c] chat, [a] agent: "
START = "Start the serving containers"
UNSAMPLED = "no evidence"
NOT_INSTALLED = "ruff was not installed"


def _policy() -> dict[str, Any]:
    (staged,) = (data_home() / "setup").iterdir()
    loaded: dict[str, Any] = yaml.safe_load(
        (staged / "policy.yaml").read_text(encoding="utf-8")
    )
    return loaded


def _said(out: str) -> list[str]:
    return [line for line in out.splitlines() if NOT_INSTALLED in line]


def test_with_no_uv_on_path_setup_goes_on_and_says_ruff_was_not_installed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sd.interactive(
        monkeypatch,
        sd.FakeRig(),
        {START: False, UNSAMPLED: False, RUFF_QUESTION: True},
        typed={USE_CASE: "m"},
    )
    nothing = tmp_path / "no-uv-here"
    nothing.mkdir()
    monkeypatch.setenv("PATH", str(nothing))

    assert cli.main(["setup"]) == 0

    (line,) = _said(capsys.readouterr().out)
    assert "uv tool install ruff" in line
    assert _policy()["gate"]["enabled"] is True, "the config was staged as asked"


@pytest.mark.parametrize(
    ("stop", "stopped_after"),
    [("config", "the config"), ("emit", "the launch specs")],
)
def test_a_run_that_stops_at_the_files_installs_nothing_and_says_how(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    stop: str,
    stopped_after: str,
) -> None:
    installed: list[str] = []
    monkeypatch.setattr(
        cli.commands.setup, "_install_ruff", lambda: installed.append("ruff")
    )
    sd.interactive(
        monkeypatch, sd.FakeRig(), {RUFF_QUESTION: True}, typed={USE_CASE: "m"}
    )

    assert cli.commands.setup.run_menu_setup(auto=False, stop=stop) == 0

    assert installed == [], f"a run stopped after {stopped_after} installs nothing"
    (line,) = _said(capsys.readouterr().out)
    assert stopped_after in line and "`uv tool install ruff`" in line
    assert _policy()["gate"]["enabled"] is True, "the config still says ruff is on"
