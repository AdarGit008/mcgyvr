"""A relief rung is full on the answers its ``relief.yaml`` entry names.

Which of the hub's answers mean "this rung cannot take the request now" is the
hub's vocabulary, and the hub client keeps it: ``mcgyvr rig rungs sync`` writes
them into each rung it keeps, as ``busy_answers`` (an HTTP status and an error
code each, :data:`mcgyvr.rig.rungs.BUSY`), and the runner reads them off the
rung's endpoint. An answer the rung names is a full rung
(:class:`~mcgyvr.capacity.SlotUnavailableError`); any other is the error it
was, the hub's old ones included.

Every server here is a loopback one this test starts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.capacity import Capacity, SlotUnavailableError
from mcgyvr.config import ConfigSchemaError, parse
from mcgyvr.pool import source_map
from mcgyvr.runner import (
    BackendError,
    Request,
    RunnerError,
    dispatch,
)
from tests.test_a_relief_rung_that_cannot_take_the_request_now_is_full import (
    KEY,
    RIDE,
    RUNG_ID,
    answering,
    error,
)
from tests.test_rig_rungs_sync_writes_only_the_relief_rungs import (
    FIRST,
    SECOND,
    Hub,
    cli,
    hub,
    setup,
)

__all__ = ["hub", "setup"]  # the fixtures the sync tests here take


@pytest.fixture(autouse=True)
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_KEY", KEY)


def ladder(address: str, busy: list[dict[str, Any]] | None) -> str:
    """A setup with one relief rung at ``address``, naming ``busy`` as its
    busy answers, or none (a ``relief.yaml`` from before they were written)."""
    rung: dict[str, Any] = {
        "address": address,
        "model": f"hitchhike@{RUNG_ID}",
        "api_key_env": "HUB_KEY",
        "width": 1,
        "position": "within",
    }
    if busy is not None:
        rung["busy_answers"] = busy
    return yaml.safe_dump(
        {
            "units": {
                "local_fast": {
                    "address": address,
                    "model": "qwen2.5-coder-3b",
                    "width": 1,
                }
            },
            "ladder": ["local_fast"],
            "fanout": "idle",
            "relief": {RIDE: rung},
        },
        sort_keys=False,
    )


def ask(
    answer: tuple[int, bytes], busy: list[dict[str, Any]] | None, tmp_path: Path
) -> tuple[Capacity, Any]:
    """What one dispatch to the relief rung ends as, when its hub answers
    ``answer``."""
    seen: list[dict[str, Any]] = []
    with answering(*answer, seen) as address:
        config = parse(ladder(address, busy))
        capacity = Capacity.of(config, root=tmp_path / "slots")
        request = Request(prompt="hello", max_output_tokens=8)
        try:
            return capacity, dispatch(
                source_map(config), RIDE, request, capacity=capacity
            )
        except Exception as exc:
            return capacity, exc


def what_a_sync_writes() -> list[dict[str, Any]]:
    from mcgyvr.rig import rungs

    return [{"status": status, "code": code} for status, code in rungs.BUSY]


def full(outcome: object) -> bool:
    return isinstance(outcome, SlotUnavailableError) and not isinstance(
        outcome, RunnerError
    )


# --- a sync writes them --------------------------------------------------------


def test_a_sync_writes_each_rungs_busy_answers_into_relief_yaml(
    setup: Path, hub: Hub
) -> None:
    from mcgyvr.config import load
    from mcgyvr.rig import rungs

    hub.answer(hub.listing(FIRST, SECOND))

    assert cli() == 0

    written = yaml.safe_load((setup / "relief.yaml").read_text(encoding="utf-8"))
    for name in (f"hitchhike-{FIRST}", f"hitchhike-{SECOND}"):
        assert written["relief"][name]["busy_answers"] == what_a_sync_writes()
        assert load(setup).relief[name].busy_answers == rungs.BUSY


def test_the_hub_client_names_the_three_answers_the_runner_was_full_on() -> None:
    from mcgyvr.rig import rungs

    assert set(rungs.BUSY) == {
        (503, "hitchhike_not_served_yet"),
        (503, "hitchhike_host_away"),
        (404, "model_not_found"),
    }
    assert len(rungs.BUSY) == len(set(rungs.BUSY))


# --- the runner reads them off the rung ----------------------------------------


def test_an_answer_the_rung_names_is_a_full_rung(tmp_path: Path) -> None:
    named = [{"status": 503, "code": "relay_warming_up"}]

    capacity, outcome = ask(error(503, "relay_warming_up"), named, tmp_path)

    assert full(outcome), outcome
    assert RIDE in str(outcome)
    assert capacity.load(RIDE) == 0, "the slot it held is given back"


@pytest.mark.parametrize(
    "answer",
    [error(503, "hitchhike_not_served_yet"), error(503, "hitchhike_host_away")],
    ids=["503-not-served-yet", "503-host-away"],
)
def test_an_answer_the_rung_does_not_name_is_that_error(
    tmp_path: Path, answer: tuple[int, bytes]
) -> None:
    """The set is the rung's: the runner holds no list of its own that a
    rung's ``busy_answers`` would only add to."""
    named = [{"status": 503, "code": "relay_warming_up"}]

    _, outcome = ask(answer, named, tmp_path)

    assert isinstance(outcome, BackendError)
    assert not isinstance(outcome, SlotUnavailableError)


def test_a_code_under_another_status_is_not_the_answer_named(tmp_path: Path) -> None:
    named = [{"status": 503, "code": "relay_warming_up"}]

    _, outcome = ask(error(500, "relay_warming_up"), named, tmp_path)

    assert isinstance(outcome, BackendError)
    assert not isinstance(outcome, SlotUnavailableError)


# --- what relief.yaml may say --------------------------------------------------


@pytest.mark.parametrize(
    ("busy", "said"),
    [
        ([], "busy_answers: is empty"),
        ([{"status": 99, "code": "x"}], "at least 100"),
        ([{"status": 600, "code": "x"}], "at most 599"),
        ([{"status": "503", "code": "x"}], "expected a number"),
        ([{"status": 503}], "code: required key is not set"),
        ([{"code": "x"}], "status: required key is not set"),
        ([{"status": 503, "code": "x", "retry": True}], "unknown key 'retry'"),
        ({"status": 503, "code": "x"}, "expected a list"),
    ],
    ids=[
        "empty",
        "below-100",
        "above-599",
        "status-text",
        "no-code",
        "no-status",
        "unknown-key",
        "not-a-list",
    ],
)
def test_busy_answers_that_do_not_read_are_refused(busy: Any, said: str) -> None:
    with pytest.raises(ConfigSchemaError, match=said):
        parse(ladder("http://127.0.0.1:9/v1", busy))
