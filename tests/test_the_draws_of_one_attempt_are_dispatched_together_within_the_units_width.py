"""The draws of one attempt are dispatched together, within the unit's width.

``best_of`` called ``sample(index)`` in a loop and the driver's ``send`` was
invoked from inside it, so N draws were N requests one after another: breadth
cost N times the latency of one draw on a unit that was declared, and
measured (CON-04), able to serve several at once.
:func:`~mcgyvr.capacity.run_batch` has bounded a batch by a capacity since #23
and had no production caller. This is the caller: every draw is a job handed
the capacity it must dispatch under, the outcomes come back in draw order, and
``best_of`` is given a ``sample`` that returns the draw already in hand. The
gate still judges the draws one at a time — there is one sandbox, and that is
inherent.

What "the draw in flight" means when several are in flight is settled here as
well: a raise is charged to the **lowest** draw that raised. The earliest is
what a reader of the journal reaches first, it is the choice that does not
depend on which thread happened to finish first, and it is what a single draw
that raised has always reported.

The width is the only limiter. On a width-1 unit the capacity's own slot
serializes the draws, and no second bound is added on top of it.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.capacity import Capacity, SlotUnavailableError
from mcgyvr.config import parse
from mcgyvr.contract import loads as load_contract
from mcgyvr.drive import Recording, worker_attempt
from mcgyvr.escalate import DispatchRaisedError
from mcgyvr.pool import Rung, source_map
from mcgyvr.route import Try, Verdict
from mcgyvr.runner import RunnerError
from mcgyvr.sandbox.tempdir import TempDirSandbox
from tests import livejournal as lj
from tests._helpers import _rows

RUNG = Rung(name="local_qwen-7b", model="qwen2.5-coder:7b")

WIDTH_ONE = lj.LADDER.replace("width: 2", "width: 1")


class _Wire:
    """A backend that counts how many requests it is serving at once.

    ``meet`` is how many callers must be inside ``generate`` at the same
    moment before any of them answers: the first ``meet`` requests wait for
    one another, so a driver that sent them one after another would leave the
    first waiting alone until the barrier gave up. ``greedy`` and ``sampled``
    are the replies, told apart by the temperature the request carries —
    draw 0 is the only greedy one.
    """

    def __init__(self, *, meet: int = 1, greedy: str, sampled: str) -> None:
        self._barrier = threading.Barrier(meet, timeout=10.0)
        self._meet = meet
        self._lock = threading.Lock()
        self._in_flight = 0
        self._greedy = greedy
        self._sampled = sampled
        self.calls = 0
        self.peak = 0

    def generate(self, model: str, request: Any) -> Any:
        with self._lock:
            self.calls += 1
            call = self.calls
            self._in_flight += 1
            self.peak = max(self.peak, self._in_flight)
        try:
            if call <= self._meet:
                self._barrier.wait()
            reply = self._greedy if request.temperature == 0.0 else self._sampled
            if reply == "raise":
                raise RunnerError("the unit closed the connection")
            return lj.completion(reply, request)
        finally:
            with self._lock:
                self._in_flight -= 1


def _attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    wire: _Wire,
    *,
    fleet: str = lj.LADDER,
    policy: str,
) -> tuple[Any, Path]:
    """One attempt through the real ``dispatch`` and a real capacity, journaled."""
    lj.patch_backend(monkeypatch, wire.generate)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = parse(fleet + policy)
    contract = load_contract(lj.MODEL_CONTRACT)
    capacity = Capacity.of(config, root=tmp_path / "slots")
    recording = Recording(path=journal / "t.jsonl", orchestrator="t")
    with TempDirSandbox(repo) as sandbox:
        attempt = worker_attempt(
            config, source_map(config), contract, sandbox, recording=recording
        )
        return attempt(Try(rung=RUNG, attempt=1, of=1, capacity=capacity)), journal


def test_three_draws_on_a_width_two_unit_go_out_two_at_a_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wire = _Wire(meet=2, greedy=lj.BAD_REPLY, sampled=lj.GOOD_REPLY)

    judgement, journal = _attempt(
        tmp_path, monkeypatch, wire, policy="breadth:\n  draws: 3\n"
    )

    assert wire.calls == 3, "every draw was dispatched"
    assert wire.peak == 2, (
        "two draws were in flight together, and never a third: the unit's "
        f"width is the bound, and the peak was {wire.peak}"
    )
    assert judgement.verdict is Verdict.PASSED
    assert (judgement.draw, judgement.draws, judgement.rows) == (1, 3, 3), (
        "the greedy reply landed on draw 0 and the first sampled one on draw 1, "
        "whichever order the unit answered in"
    )
    assert len(_rows(journal)) == 3


def test_a_width_one_unit_serializes_its_draws(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wire = _Wire(greedy=lj.BAD_REPLY, sampled=lj.BAD_REPLY)

    judgement, journal = _attempt(
        tmp_path, monkeypatch, wire, fleet=WIDTH_ONE, policy="breadth:\n  draws: 2\n"
    )

    assert wire.calls == 2
    assert wire.peak == 1, "one slot, so one draw at a time — the capacity did it"
    assert judgement.verdict is Verdict.FAILED
    assert (judgement.draws, judgement.rows) == (2, 2)
    assert len(_rows(journal)) == 2


def test_a_raise_is_charged_to_the_lowest_draw_that_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Draws 1 and 2 both die on the wire while draw 0 answers: the culprit is 1."""
    wire = _Wire(meet=2, greedy=lj.BAD_REPLY, sampled="raise")

    with pytest.raises(DispatchRaisedError) as raised:
        _attempt(tmp_path, monkeypatch, wire, policy="breadth:\n  draws: 3\n")

    assert wire.calls == 3, "a raise in one draw does not cancel the others"
    assert isinstance(raised.value.cause, RunnerError)
    assert (raised.value.draw, raised.value.draws, raised.value.rows) == (1, 3, 3), (
        "every draw reached its row, and the lowest one that raised owns the raise"
    )


def test_a_draw_declined_for_want_of_a_slot_is_skipped_not_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Draw 0 answers and draw 1 finds no slot: the attempt is judged on draw 0."""

    def one_slot_short(source_map: Any, rung: str, request: Any, **_: Any) -> Any:
        if request.temperature > 0.0:
            raise SlotUnavailableError("every slot busy for as long as it would wait")
        return lj.completion(lj.GOOD_REPLY, request)

    lj.patch_dispatch(monkeypatch, one_slot_short)
    repo = lj.make_repo(tmp_path / "repo")
    config = parse(lj.LADDER + "breadth:\n  draws: 2\n")
    contract = load_contract(lj.MODEL_CONTRACT)
    with TempDirSandbox(repo) as sandbox:
        attempt = worker_attempt(config, source_map(config), contract, sandbox)
        judgement = attempt(Try(rung=RUNG, attempt=1, of=1))

    assert judgement.verdict is Verdict.PASSED, "a decline is not a failure"
    assert (judgement.draw, judgement.draws) == (0, 2)


def test_an_attempt_whose_every_draw_was_declined_is_declined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_slot(source_map: Any, rung: str, request: Any, **_: Any) -> Any:
        raise SlotUnavailableError("every slot busy for as long as it would wait")

    lj.patch_dispatch(monkeypatch, no_slot)
    repo = lj.make_repo(tmp_path / "repo")
    config = parse(lj.LADDER + "breadth:\n  draws: 2\n")
    contract = load_contract(lj.MODEL_CONTRACT)
    with TempDirSandbox(repo) as sandbox:
        attempt = worker_attempt(config, source_map(config), contract, sandbox)
        judgement = attempt(Try(rung=RUNG, attempt=1, of=1))

    assert judgement.verdict is Verdict.DECLINED, "nothing was asked, nothing answered"
    assert judgement.draws == 2
