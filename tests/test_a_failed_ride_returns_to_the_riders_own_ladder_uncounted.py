"""A ride that fails returns the request to the rider's own ladder, uncounted.

A relief rung is ridden before the climb and is never a step of it, so what
happens on it is not what the ladder's ceilings are about: a ride that fails —
a verdict against its answer, a dispatch that raised, or a rung that could not
take the request (503, 404, an answer from another model) — spends none of the
task's attempts and none of its escalations. The request goes back to the
rider's own ladder, the entry is decided again as if the relief rung had been
full, and the climb from there has its whole budget. The ride stays in the
history, so the record says it was tried and how it ended.

Nothing here touches a network: the attempt is a script and every host is
invented.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.config import parse
from mcgyvr.escalate import Delivered, Judgement, escalate
from mcgyvr.pool import source_map
from mcgyvr.route import Try, Verdict
from tests.test_a_relief_rung_takes_work_only_when_the_riders_own_rung_is_full import (
    API,
    FAST,
    RELIEF,
    RIDE,
    SETUP,
    Script,
    capacity_of,
    contract,
    mapped,
)


class Raising(Script):
    """A script whose ride raises, as a dispatch that died does."""

    def __call__(self, this: Try) -> Judgement:
        if this.rung.name == RIDE:
            self.tried.append(RIDE)
            raise RuntimeError("the hub hung up mid-answer")
        return super().__call__(this)


@pytest.fixture(autouse=True)
def keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXAMPLE_API_KEY", "sk-" + "0" * 12)
    monkeypatch.setenv("HUB_KEY", "mhu_" + "0" * 16)


def ride_then_own(
    tmp_path: Path, script: Script, *, escalations: int = 0, setting: str = ""
) -> Delivered:
    """Escalate with the rider's own cheap rung full, so the entry is a ride."""
    config = parse(
        SETUP.format(fanout="idle", escalations=escalations) + setting + RELIEF
    )
    cap = capacity_of(config, tmp_path)
    cap.reserve(FAST)
    done = escalate(config, source_map(config), contract(), script, capacity=cap)
    assert isinstance(done, Delivered), done
    return done


def test_a_ride_the_gate_rejected_spends_no_escalation(tmp_path: Path) -> None:
    """With no escalation to spend, the rider's own api rung still takes it."""
    script = Script(**{RIDE: Verdict.FAILED, API: Verdict.PASSED})

    done = ride_then_own(tmp_path, script, escalations=0)

    assert script.tried == [RIDE, API]
    assert done.rung == API
    assert (done.attempts_spent, done.escalations) == (1, 0)


def test_a_ride_the_gate_rejected_spends_no_attempt(tmp_path: Path) -> None:
    script = Script(**{RIDE: Verdict.FAILED, API: Verdict.PASSED})

    done = ride_then_own(tmp_path, script, setting="max_attempts: 1\n")

    assert done.rung == API
    assert done.attempts_spent == 1


def test_a_ride_whose_dispatch_raised_goes_back_to_the_ladder(tmp_path: Path) -> None:
    script = Raising(**{API: Verdict.PASSED})

    done = ride_then_own(tmp_path, script, escalations=0)

    assert script.tried == [RIDE, API]
    assert (done.rung, done.attempts_spent, done.escalations) == (API, 1, 0)
    ride = done.history[0]
    assert ride.rung == RIDE and ride.raised
    assert "hung up" in ride.detail


def test_the_failed_ride_stays_in_the_record(tmp_path: Path) -> None:
    script = Script(**{RIDE: Verdict.FAILED, API: Verdict.PASSED})

    done = ride_then_own(tmp_path, script)

    assert [(a.rung, a.verdict) for a in done.history] == [
        (RIDE, Verdict.FAILED),
        (API, Verdict.PASSED),
    ]


def test_a_failed_ride_leaves_no_reservation_behind(tmp_path: Path) -> None:
    config, pool = mapped()
    cap = capacity_of(config, tmp_path)
    cap.reserve(FAST)
    script = Raising(**{API: Verdict.PASSED})

    escalate(config, pool, contract(), script, capacity=cap)
    cap.release(FAST)

    assert [cap.load(name) for name in (FAST, API, RIDE)] == [0, 0, 0]
