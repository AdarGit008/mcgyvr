"""The classifier proposer asks the Jev unit when one is bound.

The typed proposer turns a prompt and a repository into a proposal through
single-token choices, which makes each of its questions a typed decision.
With `jev.unit` bound they are asked of that unit, and the proposer exists
whether or not an orchestrator is bound, because the Jev unit is all it asks.
With no Jev unit, it asks the orchestrator's unit, as before, and an install
with neither has no typed proposer.

The wire is faked at `mcgyvr.decision._post_json`; what is asserted is the
address and model each question went to.
"""

from __future__ import annotations

from typing import Any

import pytest

import mcgyvr.decision as decision
from mcgyvr.config import parse
from mcgyvr.decision import Choice
from mcgyvr.delegate import ClassifierProposer, classifier_proposer_for
from mcgyvr.pool import source_map

ORCH = "http://localhost:18003/v1/chat/completions"
JUDGE = "http://localhost:18009/v1/chat/completions"

UNITS = """\
units:
  fast:
    address: http://localhost:18001
    model: example-coder:3b
    rig: local
  orch:
    address: http://localhost:18003
    model: example-planner:7b
    rig: local
  judge:
    address: http://localhost:18009
    model: example-judge:1b
    rig: local
ladder:
- fast
"""

ORCHESTRATOR = "orchestrator:\n  unit: orch\n  model: example-planner:7b\n"
JEV = "jev:\n  unit: judge\n"

QUESTION = {"kind": Choice("which kind?", {"docstring": "add a docstring"})}


def _wire(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Answer option A to every question; return each (url, model)."""
    sent: list[tuple[str, str]] = []
    top = [{"token": "A", "logprob": -0.1}]

    def fake_post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        sent.append((url, str(payload["model"])))
        return {"choices": [{"logprobs": {"content": [{"top_logprobs": top}]}}]}

    monkeypatch.setattr(decision, "_post_json", fake_post)
    return sent


def _proposer(text: str) -> ClassifierProposer:
    proposer = classifier_proposer_for(source_map(parse(text)))
    assert isinstance(proposer, ClassifierProposer)
    return proposer


def test_with_a_jev_unit_the_proposer_asks_it_and_not_the_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _wire(monkeypatch)
    _proposer(UNITS + ORCHESTRATOR + JEV).classify({"prompt": "x"}, QUESTION)
    assert sent == [(JUDGE, "example-judge:1b")]


def test_a_jev_unit_alone_is_enough_for_a_typed_proposer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _wire(monkeypatch)
    _proposer(UNITS + JEV).classify({"prompt": "x"}, QUESTION)
    assert sent == [(JUDGE, "example-judge:1b")]


def test_without_a_jev_unit_the_proposer_asks_the_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _wire(monkeypatch)
    _proposer(UNITS + ORCHESTRATOR).classify({"prompt": "x"}, QUESTION)
    assert sent == [(ORCH, "example-planner:7b")]


def test_with_neither_there_is_no_typed_proposer() -> None:
    assert classifier_proposer_for(source_map(parse(UNITS))) is None
