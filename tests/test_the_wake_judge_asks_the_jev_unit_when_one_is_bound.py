"""The wake judge asks the Jev unit when one is bound.

The wake judge's wake-routing judgment is a typed decision. With `jev.unit`
bound it is asked of that unit; with none, of the fast rung it was handed, as
before.

The wire is faked at `mcgyvr.decision._post_json`; what is asserted is the
address and model each request went to.
"""

from __future__ import annotations

from typing import Any

import pytest

import mcgyvr.decision as decision
from mcgyvr import wake_judge
from mcgyvr.config import parse
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
def test_the_wake_judges_judgment_asks_the_jev_unit_when_one_is_bound(
    monkeypatch: pytest.MonkeyPatch, jev: str, expected: tuple[str, str]
) -> None:
    sent = _wire(monkeypatch)
    pool = source_map(parse(UNITS + jev))
    difficulty = wake_judge.judge(pool, "fast", {"task": "x"}, timeout_s=5.0)
    assert difficulty.wake is True
    assert sent == [expected]
