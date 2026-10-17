"""``mcgyvr setup`` asks the use case, Jev and mcorch before it plans.

Owner, 2026-10-15: the interactive setup planned ``coding`` only. It now asks,
after the rigs and before the plan: the use case (coding, chat, agent or
media-gen; Enter is coding), whether to dedicate a unit to Jev, the unit every
typed decision asks (Enter is no), and, for coding with Jev on, whether to run
mcorch, the local orchestrator, on a unit (Enter is no) -- the interactive
form of ``--use-case``, ``--jev`` and ``--mcorch``. The answer is planned,
staged and sampled: the sampler runs that use case's task and the Jev choice,
and an mcorch opt-in's units are laid out awake and probed, as its lock
requires. ``media-gen`` has no sample yet: setup says so and asks before it
locks the fleet on no evidence.

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
    _SetupInteractiveError,
)
from mcgyvr.fleet import sampler
from mcgyvr.fleet.roots import data_home, fleets_dir, live_file
from tests import setup_door as sd

USE_CASE = "Use case — [d] coding (default), [c] chat, [a] agent, [m] media-gen: "
JEV = "Dedicate a unit to Jev, which answers typed decisions? [y/n] "
MCORCH = "Run mcorch, the local orchestrator, on a unit? [y/n] "
START = "Start the serving containers"
LOCK = "Lock the fleet and name it live?"
ACK = "Lock it approved on no evidence? [y/N] "


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

    def placements(rigs: Any, scans: Any) -> Any:
        at.append(len(asked))
        return planned(rigs, scans)

    monkeypatch.setattr(cli.commands.setup, "_setup_placements", placements)
    return at


def test_enter_on_every_question_plans_coding_with_no_jev_and_no_mcorch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = sd.interactive(monkeypatch, sd.FakeRig(), {START: True, LOCK: True})
    at = _planned_after(monkeypatch, asked)

    assert cli.main(["setup"]) == 0

    assert asked[:2] == [USE_CASE, JEV], "mcorch is asked only with Jev on"
    assert at == [2], "both are asked before the plan"
    assert [q.split("?")[0] for q in asked[2:]] == [f"{START} on {sd.RIG}", LOCK[:-1]]
    policy = _policy(_staged())
    assert policy["use_case"] == "coding"
    assert "jev" not in policy or not (policy["jev"] or {}).get("unit")
    assert policy["orchestrator"]["type"] != "mcorch"
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

    assert MCORCH not in asked, "mcorch is asked for coding only"
    assert _policy(_staged())["use_case"] == "chat"
    assert len(completed) == 1, "the chat sample asked the unit one completion"
    assert _policy(_live())["use_case"] == "chat"


def test_agent_is_planned_staged_and_sampled_by_the_grounded_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sd.interactive(
        monkeypatch, sd.FakeRig(), {START: True, LOCK: True}, typed={USE_CASE: "a"}
    )
    ran: list[str] = []

    def run_contract(argv: list[str]) -> int:
        contract = Path(argv[argv.index("run") + 1])
        ran.append(yaml.safe_load(contract.read_text(encoding="utf-8"))["id"])
        return sd.accepted(argv)

    monkeypatch.setattr(cli.commands.setup, "_setup_run_contract", run_contract)

    assert cli.main(["setup"]) == 0

    assert _policy(_staged())["use_case"] == "agent"
    assert ran == ["mcgyvr-sample-agent"]


@pytest.mark.parametrize("yes", [True, False])
def test_media_gen_cannot_be_sampled_yet_and_goes_to_the_acknowledgment(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], yes: bool
) -> None:
    rig = sd.FakeRig()
    asked = sd.interactive(monkeypatch, rig, {ACK: yes}, typed={USE_CASE: "m"})

    assert cli.main(["setup"]) == 0

    out = capsys.readouterr().out
    assert "media-gen cannot be sampled yet" in out
    assert not any(START in q for q in asked), "no container is started to sample"
    assert asked[-1] == ACK
    assert rig.calls == []
    assert _policy(_staged())["use_case"] == "media-gen"
    assert live_file().exists() is yes


def test_a_jev_opt_in_binds_the_unit_and_the_sample_asks_its_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = sd.interactive(
        monkeypatch, sd.FakeRig(), {START: True, LOCK: True, JEV: True}
    )
    chose: list[Path] = []

    def choose(setup: Path) -> tuple[str, float]:
        chose.append(setup)
        return "ready", 0.9

    monkeypatch.setattr(sampler, "choose", choose)

    assert cli.main(["setup"]) == 0

    assert asked[:3] == [USE_CASE, JEV, MCORCH]
    staged = _staged()
    doc = yaml.safe_load((staged / "fleet.yaml").read_text(encoding="utf-8"))
    ((unit, state),) = doc["fleets"]["own"]["layout"][sd.RIG]
    assert _policy(staged)["jev"]["unit"] == unit and state == "awake"
    assert chose == [staged], "the sample asked the Jev unit its one choice"
    assert _policy(_live())["jev"]["unit"] == unit


def test_an_mcorch_opt_in_holds_its_units_awake_samples_them_and_locks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = sd.FakeRig()
    sd.interactive(monkeypatch, rig, {START: True, LOCK: True, JEV: True, MCORCH: True})
    monkeypatch.setattr(sampler, "choose", lambda setup: ("ready", 0.9))

    assert cli.main(["setup"]) == 0

    staged = _staged()
    policy = _policy(staged)
    doc = yaml.safe_load((staged / "fleet.yaml").read_text(encoding="utf-8"))
    ((unit, state),) = doc["fleets"]["own"]["layout"][sd.RIG]
    assert policy["orchestrator"]["type"] == "mcorch"
    assert policy["orchestrator"]["unit"] == unit == policy["jev"]["unit"]
    assert policy["deployment"] == "local-only"
    assert doc["units"][unit]["window"] == sd.WINDOW
    assert state == "awake"
    assert ("read", sd.RIG, "own", (unit,), f"1x{sd.WINDOW}") in rig.calls
    assert _policy(_live())["orchestrator"]["type"] == "mcorch"


def test_a_use_case_that_is_not_one_is_asked_again_then_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked = sd.interactive(
        monkeypatch, sd.FakeRig(), {START: True}, typed={USE_CASE: "poetry"}
    )

    assert cli.main(["setup"]) == 1

    assert asked == [USE_CASE] * 3
    err = capsys.readouterr().err
    assert "poetry" in err and "d, c, a or m" in err
    assert not (data_home() / "setup").exists() or not any(
        (data_home() / "setup").rglob("policy.yaml")
    )


@pytest.mark.parametrize(
    ("letter", "name"),
    [("d", "coding"), ("c", "chat"), ("a", "agent"), ("m", "media-gen")],
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
    assert _setup_pick_unit("mcorch", ("a", "b")) == "b"
    assert asked == [
        "Which unit is Jev: a, b? [a] ",
        "Which unit runs mcorch: a, b? [a] ",
    ]
    assert _setup_pick_unit("Jev", ("only",)) == "only", "one unit is not asked"
    assert len(asked) == 2
    with pytest.raises(_SetupInteractiveError):
        _setup_pick_unit("Jev", ("a", "b"))
