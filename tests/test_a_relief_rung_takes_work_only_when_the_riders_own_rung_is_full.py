"""A relief rung takes work only when the rider's own rung is full, and never climbs.

A relief rung is another person's unit, lent through the hub ("hitchhike"). It
may serve a model above the rider's ceiling or below their floor; what it is
for is a shorter queue, not more capability. So it enters routing at exactly
one place, the spill ``fanout: idle`` already makes when a rung is full
(:meth:`~mcgyvr.escalate.Ascent.next_free_rung`), and nowhere else:

* **Only when the rider's own rung has no free slot**, by the one definition
  of full (:meth:`~mcgyvr.capacity.Capacity.judge`: this process's load or the
  server's own count at width). A free rung of the rider's own is always taken
  first.
* **Before a priced api rung.** When the rider's own family is full, a free
  relief rung is the shortest wait the ladder has, and it is chosen ahead of
  the next family up; a full one is passed over as any full rung is.
* **Never as a step of the climb.** It is on no plan of the ascent, so no
  escalation reaches it and no budget counts it: the ladder, its ceilings and
  the families a task may climb are what they were without it. ``position``
  says where the host's model sits against the rider's own, for display; it
  places nothing.
* **Only under ``fanout: idle``,** the mode that spills; ``none`` and ``full``
  never leave the family they were handed, and they never reach a relief rung.
* **A relief rung that cannot take the request now is as if it were full**:
  the climb steps aside at no cost and decides its entry again without it.

Nothing here touches a network: the attempt is a script, the capacity is built
over ``tmp_path``, and every host is invented.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.capacity import Capacity
from mcgyvr.catalog import catalog
from mcgyvr.config import Config, parse
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.escalate import (
    Assurance,
    Delivered,
    Halted,
    Judgement,
    Outcome,
    ascent,
    escalate,
)
from mcgyvr.local_pool import SourceMap, source_map
from mcgyvr.route import Try, Verdict

FAST = "local_fast"
API = "api_big"
RUNG_ID = "0f3c9a1e2b4d4c6f8a0b1c2d3e4f5a6b"
RIDE = f"hitchhike-{RUNG_ID}"
OTHER_ID = "1a2b3c4d5e6f708192a3b4c5d6e7f809"
OTHER = f"hitchhike-{OTHER_ID}"

CONTRACT = """
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["pytest -q"]
scope:
  allow: ["src/**/*.py"]
limits:
  attempts: 5
"""

SETUP = """
units:
  local_fast:
    address: http://fast-box.example:8000
    model: qwen2.5-coder-3b
    width: 1
  api_big:
    address: https://api.example.com/v1
    model: vendor-large
    width: 1
    api_key_env: EXAMPLE_API_KEY
ladder:
- local_fast
- api_big
max_escalations: {escalations}
fanout: {fanout}
"""

RELIEF = f"""
relief:
  {RIDE}:
    address: https://hub.example.org/v1
    model: hitchhike@{RUNG_ID}
    api_key_env: HUB_KEY
    width: 1
    position: above_ceiling
"""

SECOND = f"""
  {OTHER}:
    address: https://hub.example.org/v1
    model: hitchhike@{OTHER_ID}
    api_key_env: HUB_KEY
    width: 1
    position: below_floor
"""


@pytest.fixture(autouse=True)
def keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXAMPLE_API_KEY", "sk-" + "0" * 12)
    monkeypatch.setenv("HUB_KEY", "mhu_" + "0" * 16)


def mapped(
    fanout: str = "idle", *, relief: str = RELIEF, escalations: int = 1
) -> tuple[Config, SourceMap]:
    config = parse(SETUP.format(fanout=fanout, escalations=escalations) + relief)
    return config, source_map(config)


def contract() -> Contract:
    return load_contract(CONTRACT)


def capacity_of(
    config: Config, tmp_path: Path, servers: dict[str, int | None] | None = None
) -> Capacity:
    return Capacity.of(config, root=tmp_path / "slots", busy=(servers or {}).get)


def next_free(
    tmp_path: Path,
    *,
    full: tuple[str, ...] = (),
    servers: dict[str, int | None] | None = None,
    fanout: str = "idle",
    relief: str = RELIEF,
) -> str | None:
    config, pool = mapped(fanout, relief=relief)
    cap = capacity_of(config, tmp_path, servers)
    for name in full:
        cap.reserve(name)
    return ascent(config, pool, contract(), capacity=cap).next_free_rung


# --- where the spill goes ------------------------------------------------------


def test_the_riders_own_free_rung_is_taken_before_any_relief_rung(
    tmp_path: Path,
) -> None:
    assert next_free(tmp_path) == FAST


def test_a_full_own_rung_spills_to_a_free_relief_rung_before_a_priced_one(
    tmp_path: Path,
) -> None:
    assert next_free(tmp_path, full=(FAST,)) == RIDE


def test_a_full_relief_rung_is_passed_over_for_the_next_family_up(
    tmp_path: Path,
) -> None:
    assert next_free(tmp_path, full=(FAST, RIDE)) == API


def test_a_relief_rung_whose_server_count_is_at_width_is_full(
    tmp_path: Path,
) -> None:
    """The one definition of full: the server's own count fills it too."""
    assert next_free(tmp_path, full=(FAST,), servers={RIDE: 1}) == API


def test_of_two_free_relief_rungs_the_first_the_hub_listed_wins(
    tmp_path: Path,
) -> None:
    """The hub lists its rungs best first; ``position`` reorders nothing."""
    both = RELIEF + SECOND
    assert next_free(tmp_path, full=(FAST,), relief=both) == RIDE
    assert next_free(tmp_path, full=(FAST, RIDE), relief=both) == OTHER


@pytest.mark.parametrize("fanout", ["none", "full"])
def test_no_mode_but_idle_reaches_a_relief_rung(tmp_path: Path, fanout: str) -> None:
    config, pool = mapped(fanout)
    cap = capacity_of(config, tmp_path)
    cap.reserve(FAST)

    route = ascent(config, pool, contract(), capacity=cap)

    assert route.next_free_rung is None
    assert route.reserve_entry() is None


def test_a_relief_rung_whose_credential_is_unset_is_not_offered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("HUB_KEY")

    assert next_free(tmp_path, full=(FAST,)) == API


def test_the_relief_rung_stands_in_for_the_first_family_with_rungs(
    tmp_path: Path,
) -> None:
    """A floor below the local family has nothing to climb; the spill is after
    the local rungs, the rider's own, and never before them."""
    config, pool = mapped()
    cap = capacity_of(config, tmp_path)
    floor = catalog().family("deterministic")

    free = ascent(config, pool, contract(), floor=floor, capacity=cap)
    assert free.next_free_rung == FAST

    cap.reserve(FAST)
    full = ascent(config, pool, contract(), floor=floor, capacity=cap)
    assert full.next_free_rung == RIDE


def test_a_rider_whose_own_rung_is_an_api_one_rides_when_it_is_full(
    tmp_path: Path,
) -> None:
    config, pool = mapped()
    cap = capacity_of(config, tmp_path)
    cap.reserve(API)

    route = ascent(
        config, pool, contract(), floor=catalog().family("api"), capacity=cap
    )

    assert route.next_free_rung == RIDE


# --- never a step of the climb -------------------------------------------------


@pytest.mark.parametrize("fanout", ["none", "idle", "full"])
def test_a_relief_rung_is_on_no_plan_and_changes_no_budget(
    tmp_path: Path, fanout: str
) -> None:
    with_relief, pool = mapped(fanout)
    without, bare = mapped(fanout, relief="")
    cap = capacity_of(with_relief, tmp_path)

    riding = ascent(with_relief, pool, contract(), capacity=cap)
    plain = ascent(without, bare, contract())

    assert RIDE not in riding.rungs
    assert riding.rungs == plain.rungs
    assert riding.families == plain.families
    assert (riding.budget, riding.most_rungs) == (plain.budget, plain.most_rungs)


def test_the_capacity_bounds_a_relief_rung_at_the_width_the_hub_gave(
    tmp_path: Path,
) -> None:
    config, _ = mapped()

    assert capacity_of(config, tmp_path).limits[RIDE] == 1


# --- the climb -----------------------------------------------------------------


class Script:
    """An attempt function that answers from a script, per rung, and logs."""

    def __init__(self, **verdicts: Verdict) -> None:
        self._verdicts = dict(verdicts)
        self.tried: list[str] = []

    def __call__(self, this: Try) -> Judgement:
        name = this.rung.name
        self.tried.append(name)
        verdict = self._verdicts.get(name)
        if verdict is None:
            raise AssertionError(f"an unscripted attempt on {name!r}")
        if verdict is Verdict.PASSED:
            return Judgement(verdict=Verdict.PASSED, assurance=Assurance.UNVERIFIED)
        if verdict is Verdict.DECLINED:
            return Judgement(
                verdict=Verdict.DECLINED, detail="cannot take the request now"
            )
        return Judgement(verdict=Verdict.FAILED, detail="the gate rejected it")


def by_name(**verdicts: Verdict) -> Script:
    return Script(**verdicts)


def test_a_full_ladder_rides_and_a_ridden_answer_is_delivered_free_of_a_move(
    tmp_path: Path,
) -> None:
    config, pool = mapped()
    cap = capacity_of(config, tmp_path)
    cap.reserve(FAST)
    script = Script(**{RIDE: Verdict.PASSED})

    done = escalate(config, pool, contract(), script, capacity=cap)

    assert isinstance(done, Delivered)
    assert done.rung == RIDE
    assert done.escalations == 0
    assert script.tried == [RIDE]


def test_a_relief_rung_that_cannot_take_it_now_is_passed_over_as_if_full(
    tmp_path: Path,
) -> None:
    """It steps aside at no cost, and the entry is decided again without it:
    the rider's own rung is still full, so the spill goes on to the api rung."""
    config, pool = mapped()
    cap = capacity_of(config, tmp_path)
    cap.reserve(FAST)
    script = Script(**{RIDE: Verdict.DECLINED, API: Verdict.PASSED})

    done = escalate(config, pool, contract(), script, capacity=cap)

    assert isinstance(done, Delivered)
    assert done.rung == API
    assert script.tried == [RIDE, API]
    assert (done.attempts_spent, done.escalations) == (1, 0)
    assert [a.verdict for a in done.history] == [Verdict.DECLINED, Verdict.PASSED]


def test_a_ride_that_could_not_go_leaves_no_reservation_behind(
    tmp_path: Path,
) -> None:
    config, pool = mapped()
    cap = capacity_of(config, tmp_path)
    cap.reserve(FAST)
    script = Script(**{RIDE: Verdict.DECLINED, API: Verdict.PASSED})

    escalate(config, pool, contract(), script, capacity=cap)
    cap.release(FAST)

    assert {name: cap.load(name) for name in (FAST, API, RIDE)} == {
        FAST: 0,
        API: 0,
        RIDE: 0,
    }


def test_an_escalation_climbs_the_ladder_and_never_to_a_relief_rung(
    tmp_path: Path,
) -> None:
    config, pool = mapped()
    cap = capacity_of(config, tmp_path)
    script = Script(**{FAST: Verdict.FAILED, API: Verdict.PASSED})

    done = escalate(config, pool, contract(), script, capacity=cap)

    assert isinstance(done, Delivered)
    assert script.tried == [FAST, API]


def test_an_escalation_stopped_by_its_ceiling_does_not_go_on_to_a_relief_rung(
    tmp_path: Path,
) -> None:
    config, pool = mapped(escalations=0)
    cap = capacity_of(config, tmp_path)
    script = Script(**{FAST: Verdict.FAILED})

    done = escalate(config, pool, contract(), script, capacity=cap)

    assert isinstance(done, Halted)
    assert done.outcome is Outcome.ESCALATION_CEILING
    assert script.tried == [FAST]


# --- what `mcgyvr local_pool` shows --------------------------------------------------


def test_pool_shows_the_relief_rungs_apart_from_the_ladder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.cli import main
    from tests._helpers import write_setup

    folder = write_setup(
        tmp_path / "setup",
        SETUP.format(fanout="idle", escalations=1) + RELIEF + SECOND,
    )

    assert main(["local_pool", str(folder)]) == 0
    out = capsys.readouterr().out

    ladder, _, relief = out.partition("Relief rungs")
    assert RIDE not in ladder and OTHER not in ladder
    assert "2 usable rung(s)" in ladder
    assert RIDE in relief and "above_ceiling" in relief
    assert OTHER in relief and "below_floor" in relief
    assert "never climbed to" in relief
