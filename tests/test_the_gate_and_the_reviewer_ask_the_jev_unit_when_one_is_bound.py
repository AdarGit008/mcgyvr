"""The gate and the reviewer ask the Jev unit when one is bound.

The gate's Jev rung and the reviewer's typed verdict are typed decisions:
single-token questions read from next-token probabilities. With `jev.unit`
bound, each of them is asked of that unit — whether the reviewer is the named
`verifier.unit` or the dearer rung picked when none is named. Without it,
each asks the unit it asked before: the verifier's, or the reviewing rung's.
The prose half of a review is not a typed decision and stays on the reviewer.

`decision.classify_for` is the one chooser: it asks the Jev unit when bound,
and otherwise the fallback role or rung the caller names — exactly one of
them. A fallback role that turns out unbound is a named error, never `None`,
because every caller checked that it was bound before asking.

The wire is faked at `mcgyvr.decision._post_json`, so the role lookup, the
seam crossing and the label reading all run for real; what is asserted is the
address and model each request was sent to.
"""

from __future__ import annotations

from typing import Any

import pytest

import mcgyvr.decision as decision
from mcgyvr.config import parse
from mcgyvr.decision import Noul, UnboundRoleError, classify_for, jev_bound
from mcgyvr.gate.jev import jev_check_for
from mcgyvr.local_pool import SourceMap, source_map
from mcgyvr.verify import Reviewer, decider_for, reviewers_for

SMALL = "http://localhost:18001/v1/chat/completions"
BIG = "http://localhost:18002/v1/chat/completions"
JUDGE = "http://localhost:18009/v1/chat/completions"

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
  judge:
    address: http://localhost:18009
    model: example-judge:1b
    rig: local
ladder:
- small
- big
"""

NAMED_VERIFIER = UNITS + "verifier:\n  unit: big\n"
JEV = "jev:\n  unit: judge\n"


def _wire(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Answer every decision with its first label; return each (url, model).

    ``Yes`` for a yes/no question and ``0`` for a score, so a reply is
    readable whichever kind of question the gate asks.
    """
    sent: list[tuple[str, str]] = []
    top = [{"token": "Yes", "logprob": -0.1}, {"token": "0", "logprob": -0.1}]

    def fake_post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        sent.append((url, str(payload["model"])))
        return {"choices": [{"logprobs": {"content": [{"top_logprobs": top}]}}]}

    monkeypatch.setattr(decision, "_post_json", fake_post)
    return sent


def _pool(text: str) -> SourceMap:
    return source_map(parse(text))


STATE = {"change": "+x = 1\n"}
ASK = {"ok": Noul("is it ok?")}


# --- the chooser -------------------------------------------------------------


def test_jev_bound_says_whether_a_jev_unit_is_bound() -> None:
    assert jev_bound(_pool(UNITS + JEV))
    assert not jev_bound(_pool(UNITS))


def test_the_chooser_asks_the_jev_unit_when_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _wire(monkeypatch)
    classify_for(_pool(NAMED_VERIFIER + JEV), STATE, ASK, role="verifier")
    classify_for(_pool(UNITS + JEV), STATE, ASK, rung="small")
    assert sent == [(JUDGE, "example-judge:1b"), (JUDGE, "example-judge:1b")]


def test_the_chooser_asks_the_fallback_when_no_jev_unit_is_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _wire(monkeypatch)
    classify_for(_pool(NAMED_VERIFIER), STATE, ASK, role="verifier")
    classify_for(_pool(UNITS), STATE, ASK, rung="small")
    assert sent == [(BIG, "other-coder:14b"), (SMALL, "example-coder:3b")]


def test_the_chooser_takes_exactly_one_fallback() -> None:
    pool = _pool(UNITS + JEV)
    with pytest.raises(ValueError, match="role or a rung"):
        classify_for(pool, STATE, ASK)
    with pytest.raises(ValueError, match="role or a rung"):
        classify_for(pool, STATE, ASK, role="verifier", rung="small")


def test_an_unbound_fallback_role_is_a_named_error_not_none() -> None:
    with pytest.raises(UnboundRoleError, match="orchestrator"):
        classify_for(_pool(UNITS), STATE, ASK, role="orchestrator")


# --- the gate's Jev rung -----------------------------------------------------


@pytest.mark.parametrize(
    ("jev", "expected"),
    [(JEV, (JUDGE, "example-judge:1b")), ("", (BIG, "other-coder:14b"))],
)
def test_the_gates_jev_rung_asks_the_jev_unit_when_one_is_bound(
    monkeypatch: pytest.MonkeyPatch, jev: str, expected: tuple[str, str]
) -> None:
    sent = _wire(monkeypatch)
    check = jev_check_for(_pool(NAMED_VERIFIER + jev), "verifier")
    assert check is not None
    check.decide(STATE)
    assert sent and set(sent) == {expected}


# --- the reviewer's typed verdict -------------------------------------------


@pytest.mark.parametrize(
    ("jev", "expected"),
    [(JEV, (JUDGE, "example-judge:1b")), ("", (BIG, "other-coder:14b"))],
)
def test_the_named_verifiers_verdict_asks_the_jev_unit_when_one_is_bound(
    monkeypatch: pytest.MonkeyPatch, jev: str, expected: tuple[str, str]
) -> None:
    sent = _wire(monkeypatch)
    decide = decider_for(_pool(NAMED_VERIFIER + jev))
    assert decide is not None
    decide(STATE)
    assert sent == [expected]


@pytest.mark.parametrize(
    ("jev", "expected"),
    [(JEV, (JUDGE, "example-judge:1b")), ("", (BIG, "other-coder:14b"))],
)
def test_the_reviewing_rungs_typed_half_asks_the_jev_unit_when_one_is_bound(
    monkeypatch: pytest.MonkeyPatch, jev: str, expected: tuple[str, str]
) -> None:
    sent = _wire(monkeypatch)
    config = parse(UNITS + jev)
    reviewer = reviewers_for(config, source_map(config))("small")
    assert isinstance(reviewer, Reviewer)
    # Who reviews is unchanged: the dearer rung serving another model.
    assert reviewer.unit == "big"
    assert reviewer.decide is not None and reviewer.jev is not None
    reviewer.decide(STATE)
    reviewer.jev.decide(STATE)
    assert sent and set(sent) == {expected}
