"""A relief rung that cannot take the request now is a full rung, not a failure.

The hub answers a request to a relief rung it cannot serve yet with ``503``
and the code ``hitchhike_not_served_yet``, one whose host went away with
``503`` and ``hitchhike_host_away``, one whose host's unit already serves as
many rides as it may (a full ride) with ``503`` and ``pool_busy``, and one to
a rung it no longer matches this rider to (a stale ``relief.yaml``) with
``404`` and ``model_not_found``. None is a verdict on the work: nothing was
asked of a model. So the dispatch
ends as :class:`~mcgyvr.capacity.SlotUnavailableError`, the one capacity error
a climb may route around — the driver turns it into a decline, which spends no
attempt and funds no escalation, and the climb goes on as if the rung had been
full.

A host that left is not waited for: the rung is asked once and passed over,
whatever the answer says of retrying.

Only those four answers (:data:`mcgyvr.hubwire.RUNG_BUSY`), as a sync writes
them into ``relief.yaml``, and only from a relief rung. Any other error status
from a relief rung is still the error it was, and either ``503`` body from a
unit of the rider's own ladder is that unit's error. (A ladder rung's ``404``
``model_not_found`` is passed over by its own rule, with a line in the log:
``tests/test_a_rung_whose_model_is_not_known_where_it_points_is_passed_over.py``.)

Every server here is a loopback one this test starts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.capacity import Capacity, SlotUnavailableError
from mcgyvr.config import parse
from mcgyvr.local_pool import source_map
from mcgyvr.runner import (
    BackendError,
    ReliefUnavailableError,
    Request,
    RunnerError,
    dispatch,
)
from tests.rungs import KEY, RIDE, RUNG_ID, answering, error

NOT_SERVED_YET = error(503, "hitchhike_not_served_yet")
HOST_AWAY = error(503, "hitchhike_host_away")
FULL_RIDE = error(503, "pool_busy")
STALE = error(404, "model_not_found")
UNAVAILABLE = [NOT_SERVED_YET, HOST_AWAY, FULL_RIDE, STALE]
IDS = ["503", "503-host-away", "503-full-ride", "404"]


def setup(address: str) -> str:
    return f"""
units:
  local_fast:
    address: {address}
    model: qwen2.5-coder-3b
    width: 1
ladder: [local_fast]
fanout: idle
relief:
  {RIDE}:
    address: {address}
    model: hitchhike@{RUNG_ID}
    api_key_env: HUB_KEY
    width: 1
    position: within
    busy_answers: {json.dumps(what_a_sync_writes())}
"""


def what_a_sync_writes() -> list[dict[str, Any]]:
    """The rung's busy answers as ``mcgyvr rig rungs sync`` writes them."""
    from mcgyvr.rig import rungs

    ride = rungs.Ride(
        id=RUNG_ID,
        hosted_by="host",
        address="http://127.0.0.1:9/v1",
        model=f"hitchhike@{RUNG_ID}",
        served_model="coder-7b.gguf",
        width=1,
        position="within",
    )
    listing = rungs.Rides(ride=True, privacy="p", refresh_s=60.0, rungs=(ride,))
    written = yaml.safe_load(rungs.render(listing, "HUB_KEY"))
    answers: list[dict[str, Any]] = written["relief"][ride.name]["busy_answers"]
    return answers


@pytest.fixture(autouse=True)
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_KEY", KEY)


def ask(address: str, rung: str, tmp_path: Path) -> tuple[Capacity, Any]:
    config = parse(setup(address))
    capacity = Capacity.of(config, root=tmp_path / "slots")
    request = Request(prompt="hello", max_output_tokens=8)
    try:
        return capacity, dispatch(source_map(config), rung, request, capacity=capacity)
    except Exception as exc:
        return capacity, exc


@pytest.mark.parametrize("answer", UNAVAILABLE, ids=IDS)
def test_a_relief_rung_that_cannot_take_it_now_is_a_full_rung(
    tmp_path: Path, answer: tuple[int, bytes]
) -> None:
    seen: list[dict[str, Any]] = []
    with answering(*answer, seen) as address:
        capacity, outcome = ask(address, RIDE, tmp_path)

    assert isinstance(outcome, SlotUnavailableError)
    # Not a runner error, so the cooldown does not learn the rung as failing.
    assert not isinstance(outcome, RunnerError)
    assert RIDE in str(outcome)
    assert capacity.load(RIDE) == 0, "the slot it held is given back"


def test_a_full_ride_is_read_as_busy_not_as_an_error(tmp_path: Path) -> None:
    """The hub answers ``503 pool_busy`` when the host's unit serves as many
    rides as it may. The rung is full: passed over at no cost, its slot given
    back, never a ``BackendError`` the cooldown would learn it failing by."""
    seen: list[dict[str, Any]] = []
    with answering(*FULL_RIDE, seen) as address:
        capacity, outcome = ask(address, RIDE, tmp_path)

    assert isinstance(outcome, ReliefUnavailableError), outcome
    assert not isinstance(outcome, BackendError)
    assert "pool_busy" in str(outcome)
    assert len(seen) == 1
    assert capacity.load(RIDE) == 0


def test_a_ride_whose_host_went_away_is_passed_over_without_a_retry(
    tmp_path: Path,
) -> None:
    seen: list[dict[str, Any]] = []
    with answering(*HOST_AWAY, seen) as address:
        capacity, outcome = ask(address, RIDE, tmp_path)

    assert isinstance(outcome, SlotUnavailableError)
    assert len(seen) == 1, "the rung was asked once and not again"
    assert "hitchhike_host_away" in str(outcome)
    assert capacity.load(RIDE) == 0


def test_a_ride_is_asked_with_the_hubs_model_and_the_personal_key(
    tmp_path: Path,
) -> None:
    seen: list[dict[str, Any]] = []
    with answering(*NOT_SERVED_YET, seen) as address:
        ask(address, RIDE, tmp_path)

    (request,) = seen
    assert request["path"] == "/v1/chat/completions"
    assert request["authorization"] == f"Bearer {KEY}"
    assert request["body"]["model"] == f"hitchhike@{RUNG_ID}"


@pytest.mark.parametrize(
    "answer",
    [error(503, "pool_unavailable"), error(401, "invalid_api_key"), (500, b"{}")],
    ids=["503-other", "401", "500"],
)
def test_any_other_error_from_a_relief_rung_is_still_that_error(
    tmp_path: Path, answer: tuple[int, bytes]
) -> None:
    seen: list[dict[str, Any]] = []
    with answering(*answer, seen) as address:
        _, outcome = ask(address, RIDE, tmp_path)

    assert isinstance(outcome, BackendError)
    assert not isinstance(outcome, SlotUnavailableError)


@pytest.mark.parametrize("answer", [NOT_SERVED_YET, HOST_AWAY], ids=IDS[:2])
def test_the_same_answer_from_a_rung_of_the_riders_own_ladder_is_its_error(
    tmp_path: Path, answer: tuple[int, bytes]
) -> None:
    seen: list[dict[str, Any]] = []
    with answering(*answer, seen) as address:
        _, outcome = ask(address, "local_fast", tmp_path)

    assert isinstance(outcome, BackendError)
    assert not isinstance(outcome, SlotUnavailableError)
