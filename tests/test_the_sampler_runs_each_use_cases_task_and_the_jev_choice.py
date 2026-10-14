"""The sampler runs the use case's sample task and an opted-in Jev's choice.

Plan section 8.2, as :func:`mcgyvr.fleet.sample.judge` reads it: ``coding``
runs the bundled bug fix through ``mcgyvr run`` (green when the deterministic
gate passes on any rung); ``agent`` the bundled grounded contract, its reply
checked grounded and by the safety check; ``chat`` one completion per awake
unit, with the window and slots it serves read back; and an opted-in Jev unit
gives one typed choice. Every reach of a unit is a seam of
:mod:`mcgyvr.fleet.sampler` the test replaces; nothing reaches a machine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.fleet import sampler
from mcgyvr.fleet.sample import (
    TASK_CHOICE,
    TASK_COMPLETION,
    TASK_GATE,
    TASK_GROUNDED,
    TASK_SAFETY,
    Sample,
    _task_reasons,
)
from tests import sample_fleet as fx
from tests import setup_door as sd


def _setup(tmp_path: Path, use_case: str, *, jev: str | None = None) -> Path:
    policy = fx.policy_doc(tmp_path, use_case=use_case)
    if jev is not None:
        policy["jev"] = {"unit": jev}
    return fx.staged(tmp_path, policy=policy)


def test_the_bundled_samples_are_valid_contracts(tmp_path: Path) -> None:
    from mcgyvr.contract import load as load_contract

    for use_case in sampler.SAMPLES:
        bundled = sampler._bundled(use_case)
        where = tmp_path / f"{use_case}.yaml"
        where.write_text(yaml.safe_dump(bundled["contract"]), encoding="utf-8")
        assert load_contract(where).id == f"mcgyvr-sample-{use_case}"


def test_the_coding_sample_runs_the_bug_fix_on_the_staged_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = _setup(tmp_path, "coding")
    ran: list[list[str]] = []

    def run_contract(argv: list[str]) -> int:
        ran.append(argv)
        return sd.accepted(argv)

    monkeypatch.setattr(sampler, "run_contract", run_contract)

    (outcome,) = sampler.task(setup, [fx.UNIT], tmp_path / "sample")

    assert outcome.check == TASK_GATE and outcome.passed
    (argv,) = ran
    assert argv[0] == "run" and argv[argv.index("--config") + 1] == str(setup)
    repo = Path(argv[argv.index("--repo") + 1])
    assert (repo / "calc.py").read_text(encoding="utf-8").strip().endswith("a - b")
    assert (repo / ".git").is_dir()


def test_the_agent_sample_is_grounded_and_safety_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    setup = _setup(tmp_path, "agent")
    reference = sampler._bundled("agent")["reference"]["answer"]

    def run_contract(argv: list[str]) -> int:
        where = Path(argv[argv.index("--result") + 1])
        where.write_text(
            json.dumps({"outcome": "accepted", "rung": fx.UNIT, "answer": reference}),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(sampler, "run_contract", run_contract)
    monkeypatch.setattr(sampler, "safe", lambda answer: None)

    grounded, safety = sampler.task(setup, [fx.UNIT], tmp_path / "sample")

    assert (grounded.check, grounded.passed) == (TASK_GROUNDED, True)
    assert (safety.check, safety.passed) == (TASK_SAFETY, True)


def test_a_reply_that_does_not_cite_or_state_the_source_is_not_grounded() -> None:
    assert (
        sampler.grounded("The sky was green [1]. Tuesday [1].", "[1]", ["green"])
        is None
    )
    assert "cite" in str(sampler.grounded("The sky was green.", "[1]", ["green"]))
    assert "tuesday" in str(
        sampler.grounded("The sky was green [1].", "[1]", ["green", "tuesday"])
    )


def test_a_safety_check_that_cannot_run_is_a_reason_not_a_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil

    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert "could not run" in str(sampler.safe("The sky was green [1]."))


def test_the_chat_sample_completes_once_per_unit_and_reads_back_what_it_serves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = _setup(tmp_path, "chat")
    asked: list[str] = []

    def complete(where: Path, unit: str) -> str:
        asked.append(unit)
        return "ready"

    monkeypatch.setattr(sampler, "complete", complete)
    monkeypatch.setattr(sampler, "served", lambda unit: {"window": 8192, "slots": 4})

    (outcome,) = sampler.task(setup, [fx.UNIT], tmp_path / "sample")

    assert asked == [fx.UNIT]
    assert outcome.check == TASK_COMPLETION and outcome.passed
    fleet = fx.fleet_doc()
    assert _task_reasons("chat", fleet, [fx.UNIT], None, [outcome]) == []


def test_a_chat_unit_serving_another_window_than_planned_is_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = _setup(tmp_path, "chat")
    monkeypatch.setattr(sampler, "complete", lambda where, unit: "ready")
    monkeypatch.setattr(sampler, "served", lambda unit: {"window": 4096, "slots": 4})

    outcomes = sampler.task(setup, [fx.UNIT], tmp_path / "sample")

    (why,) = _task_reasons("chat", fx.fleet_doc(), [fx.UNIT], None, outcomes)
    assert "served window 4096, planned 8192" in why


def test_an_opted_in_jev_unit_gives_one_typed_choice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = _setup(tmp_path, "coding", jev=fx.UNIT)
    monkeypatch.setattr(sampler, "run_contract", sd.accepted)
    monkeypatch.setattr(sampler, "choose", lambda where: ("ready", 0.93))

    outcomes: list[Any] = sampler.task(setup, [fx.UNIT], tmp_path / "sample")

    choice = next(one for one in outcomes if one.check == TASK_CHOICE)
    assert (choice.unit, choice.label, choice.probability) == (fx.UNIT, "ready", 0.93)


def test_a_jev_unit_that_cannot_answer_is_a_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = _setup(tmp_path, "coding", jev=fx.UNIT)
    monkeypatch.setattr(sampler, "run_contract", sd.accepted)

    def refused(where: Path) -> tuple[str, float]:
        raise sampler.SamplerError("jev.unit binds no unit")

    monkeypatch.setattr(sampler, "choose", refused)

    outcomes = sampler.task(setup, [fx.UNIT], tmp_path / "sample")

    choice = next(one for one in outcomes if one.check == TASK_CHOICE)
    assert not choice.passed and "binds no unit" in choice.why


def test_a_media_gen_fleet_has_no_sample_task(tmp_path: Path) -> None:
    setup = _setup(tmp_path, "media-gen")
    assert sampler.task(setup, [fx.UNIT], tmp_path / "sample") == []
    sample = Sample(setup=setup, fleet=fx.FLEET, reads=())
    assert sample.outcomes == ()
