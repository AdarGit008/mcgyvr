"""The fleet and ladder managers ask the Jev unit, and never sleep its card.

The fleet manager's wake-routing judgment and the ladder manager's choices
are typed decisions. With `jev.unit` bound they are asked of that unit; with
none, of the fast rung each was handed, as before. The ladder manager never
puts to sleep the card its decisions run on, so `mcgyvr manage` hands it the
Jev unit's name when one is bound, and the fast rung's when not.

The wire is faked at `mcgyvr.decision._post_json`; what is asserted is the
address and model each request went to.
"""

from __future__ import annotations

import argparse
from typing import Any

import pytest

import mcgyvr.decision as decision
from mcgyvr import cli, fleet_manager, ladder_manager
from mcgyvr.config import Config, parse
from mcgyvr.local_pool import source_map

FAST = "http://localhost:18001/v1/chat/completions"
JUDGE = "http://localhost:18009/v1/chat/completions"

UNITS = """\
units:
  fast:
    address: http://localhost:18001
    model: example-coder:3b
    rig: local
  big:
    address: http://localhost:18002
    model: other-coder:14b
    rig: local
  judge:
    address: http://localhost:18009
    model: example-judge:1b
    rig: local
ladder:
- fast
- big
"""

JEV = "jev:\n  unit: judge\n"

BOUND = [(JEV, (JUDGE, "example-judge:1b")), ("", (FAST, "example-coder:3b"))]


def _wire(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Answer Yes, or option A, to every decision; return each (url, model)."""
    sent: list[tuple[str, str]] = []
    top = [{"token": "Yes", "logprob": -0.1}, {"token": "A", "logprob": -0.1}]

    def fake_post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        sent.append((url, str(payload["model"])))
        return {"choices": [{"logprobs": {"content": [{"top_logprobs": top}]}}]}

    monkeypatch.setattr(decision, "_post_json", fake_post)
    return sent


@pytest.mark.parametrize(("jev", "expected"), BOUND)
def test_the_fleet_managers_judgment_asks_the_jev_unit_when_one_is_bound(
    monkeypatch: pytest.MonkeyPatch, jev: str, expected: tuple[str, str]
) -> None:
    sent = _wire(monkeypatch)
    pool = source_map(parse(UNITS + jev))
    difficulty = fleet_manager.judge(pool, "fast", {"task": "x"}, timeout_s=5.0)
    assert difficulty.wake is True
    assert sent == [expected]


@pytest.mark.parametrize(("jev", "expected"), BOUND)
def test_the_ladder_managers_decisions_ask_the_jev_unit_when_one_is_bound(
    monkeypatch: pytest.MonkeyPatch, jev: str, expected: tuple[str, str]
) -> None:
    sent = _wire(monkeypatch)
    pool = source_map(parse(UNITS + jev))
    decide = ladder_manager.decide_on(pool, "fast", timeout_s=5.0)
    question = decision.Choice("which?", {"stay": "stay", "move": "move"})
    answer = decide({"queue": 0}, {"pick": question}).answers["pick"]
    assert isinstance(answer, decision.ChoiceAnswer) and answer.choice == "stay"
    assert sent == [expected]


class _StopError(Exception):
    """Raised by the captured view so the manager is never built."""


@pytest.mark.parametrize(("jev", "spared"), [(JEV, "judge"), ("", "fast")])
def test_manage_never_sleeps_the_card_its_decisions_run_on(
    monkeypatch: pytest.MonkeyPatch, jev: str, spared: str
) -> None:
    seen: list[str] = []

    def view_of(config: Config, *, jev: str) -> ladder_manager.View:
        seen.append(jev)
        raise _StopError

    monkeypatch.setattr(ladder_manager.View, "of", view_of)
    config = parse(UNITS + jev)
    with pytest.raises(_StopError):
        cli._manage_held(argparse.Namespace(once=True), config)
    assert seen == [spared]
