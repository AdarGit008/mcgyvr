"""``mcgyvr setup --deployment`` opens the wizard, and the agent slots are planned.

``--deployment`` answers a question the wizard asks itself, so on a terminal
it is carried into the wizard rather than making the run the flag path: the
use case is still asked, the deployment question is not, and the staged
policy says the deployment the flag named. The agent branch asks how many
requests a unit serves at once; that count is what the plan places for, and
the staged policy and each unit say it.

The rig is :class:`tests.setup_door.FakeRig` behind the door; the prompts are
answered through the setup's own prompt seams; nothing reaches a machine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr import cli
from mcgyvr.cli.commands.setup import DEPLOYMENT_QUESTION, SLOTS_QUESTION
from mcgyvr.fleet.roots import data_home
from tests import setup_door as sd

USE_CASE = "Use case — [m] mcgyvr-code, [k] code, [c] chat, [a] agent: "
START = "Start the serving containers"
UNSAMPLED = "no evidence"


def _staged() -> Path:
    (staged,) = (data_home() / "setup").iterdir()
    return staged


def _read(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(
        (_staged() / name).read_text(encoding="utf-8")
    )
    return loaded


def test_deployment_on_a_terminal_opens_the_wizard_and_is_not_asked_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = sd.interactive(
        monkeypatch,
        sd.FakeRig(),
        {START: False, UNSAMPLED: False},
        typed={USE_CASE: "m"},
    )

    assert cli.main(["setup", "--deployment", "local-only"]) == 0

    assert asked[0] == USE_CASE, "the wizard ran, not the flag path"
    assert DEPLOYMENT_QUESTION not in asked, "the flag answered it"
    assert _read("policy.yaml")["deployment"] == "local-only"


def test_the_agent_slot_count_is_planned_and_staged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = sd.interactive(
        monkeypatch,
        sd.FakeRig(),
        {START: False, UNSAMPLED: False},
        typed={USE_CASE: "a", SLOTS_QUESTION: "4"},
    )
    planned = cli.commands.setup._setup_placements
    users: list[int] = []

    def placements(rigs: Any, scans: Any, use_case: str, **kwargs: Any) -> Any:
        users.append(kwargs["users"])
        return planned(rigs, scans, use_case, **kwargs)

    monkeypatch.setattr(cli.commands.setup, "_setup_placements", placements)

    assert cli.main(["setup"]) == 0

    assert SLOTS_QUESTION in asked
    assert users == [4], "the plan places for the slots asked"
    assert _read("policy.yaml")["users"] == 4
    units = [u for u in _read("fleet.yaml")["units"].values() if "rig" in u]
    assert units and all(unit["width"] == 4 for unit in units)
