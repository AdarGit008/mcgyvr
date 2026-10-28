"""``mcgyvr setup`` asks the use case and Jev before it plans.

The interactive setup planned one use case only. It now asks,
after the rigs and before the plan: the use case (mcgyvr-code, code, chat or
agent; there is no Enter default, because choosing mcgyvr-code is the act of
opting in) and, for mcgyvr-code only, whether to dedicate a unit to Jev, the
unit every typed decision asks (Enter is no) -- the interactive form of
``--use-case`` and ``--jev``. The raw use cases have no Jev in their path.
The answer is planned, staged and sampled: the sampler runs that use case's
task and the Jev choice.

The rig is :class:`tests.setup_door.FakeRig` behind the door; the prompts are
answered through the setup's own prompt seams; nothing reaches a machine.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr import cli
from mcgyvr.cli.commands.setup import (
    _ask_setup_use_case,
    _setup_pick_unit,
    _setup_placements,
    _setup_use_cases,
    _SetupInteractiveError,
)
from mcgyvr.fleet import sampler
from mcgyvr.fleet.roots import data_home, fleets_dir, live_file
from tests import setup_door as sd

USE_CASE = "Use case — [m] mcgyvr-code, [k] code, [c] chat, [a] agent: "
JEV = "Dedicate a unit to Jev, which answers typed decisions? [y/n] "
START = "Start the serving containers"
LOCK = "Lock the fleet and name it live?"


def _staged() -> Path:
    (staged,) = (data_home() / "setup").iterdir()
    return staged


def _policy(where: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(
        (where / "policy.yaml").read_text(encoding="utf-8")
    )
    return loaded


def _live() -> Path:
    name = json.loads(live_file().read_text(encoding="utf-8"))["fleet"]
    return fleets_dir() / str(name)


def _planned_after(monkeypatch: pytest.MonkeyPatch, asked: list[str]) -> list[int]:
    """How many questions had been asked when the plan was made."""
    at: list[int] = []
    planned = _setup_placements

    def placements(rigs: Any, scans: Any, use_case: str) -> Any:
        at.append(len(asked))
        return planned(rigs, scans, use_case)

    monkeypatch.setattr(cli.commands.setup, "_setup_placements", placements)
    return at


def test_mcgyvr_code_and_enter_on_jev_plans_mcgyvr_code_with_no_jev(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = sd.interactive(
        monkeypatch, sd.FakeRig(), {START: True, LOCK: True}, typed={USE_CASE: "m"}
    )
    at = _planned_after(monkeypatch, asked)

    assert cli.main(["setup"]) == 0

    assert asked[:2] == [USE_CASE, JEV]
    assert at == [2], "both are asked before the plan"
    assert [q.split("?")[0] for q in asked[2:]] == [f"{START} on {sd.RIG}", LOCK[:-1]]
    policy = _policy(_staged())
    assert policy["use_case"] == "mcgyvr-code"
    assert "jev" not in policy or not (policy["jev"] or {}).get("unit")
    assert live_file().exists()


def test_chat_is_planned_staged_and_sampled_by_one_completion_of_each_unit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = sd.interactive(
        monkeypatch, sd.FakeRig(), {START: True, LOCK: True}, typed={USE_CASE: "c"}
    )
    completed: list[str] = []

    def complete(setup: Path, unit: str) -> str:
        completed.append(unit)
        return "ready"

    monkeypatch.setattr(sampler, "complete", complete)
    monkeypatch.setattr(
        sampler, "served", lambda unit: {"window": sd.WINDOW, "slots": 1}
    )

    assert cli.main(["setup"]) == 0

    assert asked[0] == USE_CASE and JEV not in asked, "chat is raw: no Jev"
    assert _policy(_staged())["use_case"] == "chat"
    assert len(completed) == 1, "the chat sample asked the unit one completion"
    assert _policy(_live())["use_case"] == "chat"


def test_agent_is_planned_staged_and_sampled_by_the_grounded_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sd.interactive(
        monkeypatch, sd.FakeRig(), {START: True, LOCK: True}, typed={USE_CASE: "a"}
    )
    asked: list[str] = []
    reference = sampler._bundled("agent")["reference"]["answer"]

    def ground(setup: Path, unit: str) -> str:
        asked.append(unit)
        return str(reference)

    monkeypatch.setattr(sampler, "ground", ground)

    assert cli.main(["setup"]) == 0

    assert _policy(_staged())["use_case"] == "agent"
    assert len(asked) == 1, "the agent sample asked one unit its question"
    # The grounded check (citations and facts) is the agent sample's only
    # task check, so the reference reply samples green and the fleet is locked.
    assert _policy(_live())["use_case"] == "agent"


def test_a_jev_opt_in_binds_the_unit_and_the_sample_asks_its_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = sd.interactive(
        monkeypatch,
        sd.FakeRig(),
        {START: True, LOCK: True, JEV: True},
        typed={USE_CASE: "m"},
    )
    chose: list[Path] = []

    def choose(setup: Path) -> tuple[str, float]:
        chose.append(setup)
        return "ready", 0.9

    monkeypatch.setattr(sampler, "choose", choose)

    assert cli.main(["setup"]) == 0

    assert asked[:2] == [USE_CASE, JEV]
    assert asked[2].startswith(START), "Jev is the last question before the plan"
    staged = _staged()
    doc = yaml.safe_load((staged / "fleet.yaml").read_text(encoding="utf-8"))
    ((unit, state),) = doc["fleets"]["own"]["layout"][sd.RIG]
    assert _policy(staged)["jev"]["unit"] == unit and state == "awake"
    assert chose == [staged], "the sample asked the Jev unit its one choice"
    assert _policy(_live())["jev"]["unit"] == unit


def test_a_use_case_that_is_not_one_is_asked_again_then_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked = sd.interactive(
        monkeypatch, sd.FakeRig(), {START: True}, typed={USE_CASE: "poetry"}
    )

    assert cli.main(["setup"]) == 1

    assert asked == [USE_CASE] * 3
    err = capsys.readouterr().err
    assert "poetry" in err and "m, k, c or a" in err
    assert not (data_home() / "setup").exists() or not any(
        (data_home() / "setup").rglob("policy.yaml")
    )


@pytest.mark.parametrize(
    ("letter", "name"),
    [
        ("m", "mcgyvr-code"),
        ("k", "code"),
        ("c", "chat"),
        ("a", "agent"),
        ("mcgyvr-code", "mcgyvr-code"),
        ("code", "code"),
    ],
)
def test_each_letter_names_its_use_case(
    monkeypatch: pytest.MonkeyPatch, letter: str, name: str
) -> None:
    asked: list[str] = []

    def ask(question: str, prompt: Any = None) -> str:
        asked.append(question)
        return letter

    monkeypatch.setattr(cli.commands.setup, "_ask", ask)

    assert _ask_setup_use_case() == name
    assert asked == [USE_CASE]


def test_a_letter_that_names_no_use_case_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked = sd.interactive(
        monkeypatch, sd.FakeRig(), {START: True}, typed={USE_CASE: "d"}
    )

    assert cli.main(["setup"]) == 1

    assert asked == [USE_CASE] * 3
    assert "m, k, c or a" in capsys.readouterr().err


def test_enter_is_no_use_case_it_is_asked_again_then_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked = sd.interactive(
        monkeypatch, sd.FakeRig(), {START: True}, typed={USE_CASE: ""}
    )

    assert cli.main(["setup"]) == 1

    assert asked == [USE_CASE] * 3
    assert "pick one" in capsys.readouterr().out


def test_setup_offers_four_use_cases_mcgyvr_code_first() -> None:
    assert _setup_use_cases() == ("mcgyvr-code", "code", "chat", "agent")


def test_a_use_case_setup_never_offered_is_refused_naming_the_four(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["setup", "--use-case", "poetry"]) == 1

    (line,) = capsys.readouterr().err.splitlines()
    assert (
        "`poetry` is not a use case" in line
        and "mcgyvr-code, code, chat or agent" in line
    )
    assert not (data_home() / "setup").exists(), "nothing is staged"


def test_with_several_units_setup_asks_which_one_and_enter_is_the_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []
    answers = iter(["", "b", "nope", "nope", "nope"])

    def ask(question: str, prompt: Any = None) -> str:
        asked.append(question)
        return next(answers)

    monkeypatch.setattr(cli.commands.setup, "_ask", ask)

    assert _setup_pick_unit("Jev", ("a", "b")) == "a"
    assert _setup_pick_unit("Jev", ("a", "b")) == "b"
    assert asked == ["Which unit is Jev: a, b? [a] "] * 2
    assert _setup_pick_unit("Jev", ("only",)) == "only", "one unit is not asked"
    assert len(asked) == 2
    with pytest.raises(_SetupInteractiveError):
        _setup_pick_unit("Jev", ("a", "b"))
