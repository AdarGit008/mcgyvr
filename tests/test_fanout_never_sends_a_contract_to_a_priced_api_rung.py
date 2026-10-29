"""Fan-out never sends a contract to a priced api rung (F28).

Fan-out, ``idle`` or ``full``, spreads work over your own rungs and the relief
rungs lent to you, and nowhere else. When every own rung is full and no relief
rung has room, the contract waits on its own ladder: fan-out does not enter it
at an api rung. Escalation up the ladder is not fan-out. A climb that spends its
own rungs still reaches the api rungs, in the order the ladder lists them, so a
busy cheap api rung is not passed over for a dearer free one either.

Nothing here touches a network: the attempt is a script, the capacity is built
over ``tmp_path``, and every host is invented.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.catalog import catalog
from mcgyvr.config import parse
from mcgyvr.escalate import Delivered, ascent, escalate
from mcgyvr.local_pool import source_map
from mcgyvr.route import Verdict
from tests.relieftakes import (
    API,
    FAST,
    Script,
    capacity_of,
    contract,
    mapped,
)
from tests.rungs import RIDE

SPREADING = ("idle", "full")

SMALL = "api_small"

TWO_PRICED = """
units:
  local_fast:
    address: http://fast-box.example:8000
    model: qwen2.5-coder-3b
    width: 1
  api_small:
    address: https://small.example.com/v1
    model: vendor-small
    width: 1
    api_key_env: EXAMPLE_API_KEY
  api_big:
    address: https://big.example.com/v1
    model: vendor-large
    width: 1
    api_key_env: EXAMPLE_API_KEY
ladder:
- local_fast
- api_small
- api_big
fanout: {fanout}
"""


@pytest.fixture(autouse=True)
def keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXAMPLE_API_KEY", "sk-" + "0" * 12)
    monkeypatch.setenv("HUB_KEY", "mhu_" + "0" * 16)


# --- the entry: every own rung full ---------------------------------------------


@pytest.mark.parametrize("fanout", SPREADING)
def test_with_every_own_rung_full_fanout_enters_no_api_rung(
    tmp_path: Path, fanout: str
) -> None:
    config, pool = mapped(fanout, relief="")
    cap = capacity_of(config, tmp_path)
    cap.reserve(FAST)

    route = ascent(config, pool, contract(), capacity=cap)

    assert route.next_free_rung is None
    assert route.reserve_entry() is None
    assert cap.load(API) == 0, "deciding the entry claimed nothing priced"


@pytest.mark.parametrize("fanout", SPREADING)
def test_with_every_own_rung_full_the_contract_climbs_its_own_ladder_first(
    tmp_path: Path, fanout: str
) -> None:
    """The contract queues on its own rung; the api rung is reached only by
    escalating, and that move is counted."""
    config, pool = mapped(fanout, relief="")
    cap = capacity_of(config, tmp_path)
    cap.reserve(FAST)
    script = Script(**{FAST: Verdict.FAILED, API: Verdict.PASSED})

    done = escalate(config, pool, contract(), script, capacity=cap)

    assert isinstance(done, Delivered)
    assert script.tried == [FAST, API]
    assert (done.rung, done.escalations) == (API, 1)


def test_with_every_own_and_relief_rung_full_idle_enters_no_api_rung(
    tmp_path: Path,
) -> None:
    config, pool = mapped("idle")
    cap = capacity_of(config, tmp_path)
    cap.reserve(FAST)
    cap.reserve(RIDE)
    script = Script(**{FAST: Verdict.FAILED, API: Verdict.PASSED})

    assert ascent(config, pool, contract(), capacity=cap).next_free_rung is None

    done = escalate(config, pool, contract(), script, capacity=cap)

    assert isinstance(done, Delivered)
    assert script.tried == [FAST, API]


# --- relief is ridden as before --------------------------------------------------


def test_idle_still_rides_a_free_relief_rung_when_the_own_rung_is_full(
    tmp_path: Path,
) -> None:
    config, pool = mapped("idle")
    cap = capacity_of(config, tmp_path)
    cap.reserve(FAST)
    script = Script(**{RIDE: Verdict.PASSED})

    assert ascent(config, pool, contract(), capacity=cap).next_free_rung == RIDE

    done = escalate(config, pool, contract(), script, capacity=cap)

    assert isinstance(done, Delivered)
    assert (done.rung, done.escalations) == (RIDE, 0)
    assert script.tried == [RIDE]


def test_a_relief_rung_that_cannot_take_it_now_hands_back_to_the_own_ladder(
    tmp_path: Path,
) -> None:
    """After a ride steps aside, the entry is decided again without relief, and
    a full own ladder still sends nothing straight to the api rung."""
    config, pool = mapped("idle")
    cap = capacity_of(config, tmp_path)
    cap.reserve(FAST)
    script = Script(
        **{RIDE: Verdict.DECLINED, FAST: Verdict.FAILED, API: Verdict.PASSED}
    )

    done = escalate(config, pool, contract(), script, capacity=cap)

    assert isinstance(done, Delivered)
    assert script.tried == [RIDE, FAST, API]
    assert (done.rung, done.escalations) == (API, 1)


# --- escalation is not fan-out ---------------------------------------------------


@pytest.mark.parametrize("fanout", ("none", *SPREADING))
def test_a_climb_that_ends_on_an_api_rung_still_escalates_there(
    tmp_path: Path, fanout: str
) -> None:
    config, pool = mapped(fanout, relief="")
    cap = capacity_of(config, tmp_path)
    script = Script(**{FAST: Verdict.FAILED, API: Verdict.PASSED})

    done = escalate(config, pool, contract(), script, capacity=cap)

    assert isinstance(done, Delivered)
    assert script.tried == [FAST, API]
    assert (done.rung, done.escalations) == (API, 1)


@pytest.mark.parametrize("fanout", SPREADING)
def test_escalation_takes_the_api_rungs_in_ladder_order_however_busy(
    tmp_path: Path, fanout: str
) -> None:
    """Fan-out does not pass a busy cheap api rung over for a dearer free one."""
    config = parse(TWO_PRICED.format(fanout=fanout))
    pool = source_map(config)
    cap = capacity_of(config, tmp_path)
    cap.reserve(SMALL)
    script = Script(**{SMALL: Verdict.FAILED, API: Verdict.PASSED})

    done = escalate(
        config,
        pool,
        contract(),
        script,
        floor=catalog().family("api"),
        capacity=cap,
    )

    assert isinstance(done, Delivered)
    assert script.tried == [SMALL, API]


# --- `none` is unchanged ---------------------------------------------------------


def test_fanout_none_queues_on_the_own_rung_as_it_did(tmp_path: Path) -> None:
    config, pool = mapped("none")
    cap = capacity_of(config, tmp_path)
    cap.reserve(FAST)
    script = Script(**{FAST: Verdict.FAILED, API: Verdict.PASSED})

    route = ascent(config, pool, contract(), capacity=cap)
    assert (route.next_free_rung, route.reserve_entry()) == (None, None)

    done = escalate(config, pool, contract(), script, capacity=cap)

    assert isinstance(done, Delivered)
    assert script.tried == [FAST, API]
    assert (done.rung, done.escalations) == (API, 1)
