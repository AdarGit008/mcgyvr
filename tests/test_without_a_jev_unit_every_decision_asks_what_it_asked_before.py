"""Without a Jev unit, every typed decision asks what it asked before.

The `jev:` block is backward compatible by construction: with no block, or
with the block `mcgyvr init` writes (`unit` and `model` unset), each typed
decision goes to exactly the unit it went to before the block existed —

* the gate's Jev rung and the named reviewer's verdict to `verifier.unit`;
* a picked reviewer's verdict and gate questions to the dearer rung that
  reviews, the one serving a model other than the builder's;
* the fleet manager's wake judgment and the ladder manager's choices to the
  fast rung, the cheapest resident one;
* the typed proposer's choices to `orchestrator.unit`.

The wire is faked at `mcgyvr.decision._post_json`; what is asserted is the
address and model of every request, so a decision that strayed to another
unit fails here whichever caller sent it.
"""

from __future__ import annotations

from typing import Any

import pytest

import mcgyvr.decision as decision
from mcgyvr import fleet_manager, ladder_manager
from mcgyvr.config import Config, parse
from mcgyvr.decision import Choice
from mcgyvr.delegate import ClassifierProposer, classifier_proposer_for
from mcgyvr.gate.jev import jev_check_for
from mcgyvr.pool import SourceMap, source_map
from mcgyvr.verify import Reviewer, decider_for, reviewers_for

SMALL = ("http://localhost:18001/v1/chat/completions", "example-coder:3b")
BIG = ("http://localhost:18002/v1/chat/completions", "other-coder:14b")
ORCH = ("http://localhost:18003/v1/chat/completions", "example-planner:7b")
REV = ("http://localhost:18004/v1/chat/completions", "example-reviewer:7b")

UNITS = """\
units:
  small:
    address: http://localhost:18001
    model: example-coder:3b
    rig: local
  big:
    address: http://localhost:18002
    model: other-coder:14b
    rig: local
  orch:
    address: http://localhost:18003
    model: example-planner:7b
    rig: local
  rev:
    address: http://localhost:18004
    model: example-reviewer:7b
    rig: local
ladder:
- small
- big
orchestrator:
  unit: orch
  model: example-planner:7b
"""

NAMED = "verifier:\n  enabled: true\n  unit: rev\n"

#: No block at all, and the block init writes: both are "no Jev unit".
NO_JEV = pytest.mark.parametrize(
    "jev", ["", "jev:\n  unit: null\n  model: null\n"], ids=["absent", "as-init"]
)

STATE = {"change": "+x = 1\n"}


def _wire(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Answer every question with its first label; return each (url, model)."""
    sent: list[tuple[str, str]] = []
    top = [
        {"token": "Yes", "logprob": -0.1},
        {"token": "0", "logprob": -0.1},
        {"token": "A", "logprob": -0.1},
    ]

    def fake_post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        sent.append((url, str(payload["model"])))
        return {"choices": [{"logprobs": {"content": [{"top_logprobs": top}]}}]}

    monkeypatch.setattr(decision, "_post_json", fake_post)
    return sent


def _loaded(text: str) -> tuple[Config, SourceMap]:
    config = parse(text)
    return config, source_map(config)


@NO_JEV
def test_the_gates_jev_rung_asks_the_named_verifier(
    monkeypatch: pytest.MonkeyPatch, jev: str
) -> None:
    sent = _wire(monkeypatch)
    _, pool = _loaded(UNITS + NAMED + jev)
    check = jev_check_for(pool, "verifier")
    assert check is not None
    check.decide(STATE)
    assert sent and set(sent) == {REV}


@NO_JEV
def test_the_named_reviewers_verdict_asks_the_named_verifier(
    monkeypatch: pytest.MonkeyPatch, jev: str
) -> None:
    sent = _wire(monkeypatch)
    _, pool = _loaded(UNITS + NAMED + jev)
    decide = decider_for(pool)
    assert decide is not None
    decide(STATE)
    assert sent == [REV]


@NO_JEV
def test_a_picked_reviewer_asks_the_dearer_independent_rung(
    monkeypatch: pytest.MonkeyPatch, jev: str
) -> None:
    sent = _wire(monkeypatch)
    config, pool = _loaded(UNITS + jev)
    reviewer = reviewers_for(config, pool)("small")
    assert isinstance(reviewer, Reviewer)
    assert reviewer.decide is not None and reviewer.jev is not None
    reviewer.decide(STATE)
    reviewer.jev.decide(STATE)
    assert sent and set(sent) == {BIG}


@NO_JEV
def test_the_fleet_managers_judgment_asks_the_fast_rung(
    monkeypatch: pytest.MonkeyPatch, jev: str
) -> None:
    sent = _wire(monkeypatch)
    config, pool = _loaded(UNITS + jev)
    fast = fleet_manager.fast_rung(config, pool)
    assert fast is not None and fast.name == "small"
    fleet_manager.judge(pool, fast.name, {"task": "x"}, timeout_s=5.0)
    assert sent == [SMALL]


@NO_JEV
def test_the_ladder_managers_decisions_ask_the_fast_rung(
    monkeypatch: pytest.MonkeyPatch, jev: str
) -> None:
    sent = _wire(monkeypatch)
    config, pool = _loaded(UNITS + jev)
    fast = fleet_manager.fast_rung(config, pool)
    assert fast is not None
    decide = ladder_manager.decide_on(pool, fast.name, timeout_s=5.0)
    decide({"queue": 0}, {"pick": Choice("which?", {"stay": "stay"})})
    assert sent == [SMALL]


@NO_JEV
def test_the_typed_proposer_asks_the_orchestrator(
    monkeypatch: pytest.MonkeyPatch, jev: str
) -> None:
    sent = _wire(monkeypatch)
    _, pool = _loaded(UNITS + jev)
    proposer = classifier_proposer_for(pool)
    assert isinstance(proposer, ClassifierProposer)
    proposer.classify({"prompt": "x"}, {"kind": Choice("which?", {"a": "a"})})
    assert sent == [ORCH]
