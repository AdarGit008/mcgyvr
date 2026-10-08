"""A relief rung is full on the answers its ``relief.yaml`` entry names.

Which of the hub's answers mean "this rung cannot take the request now" is the
hub's vocabulary, and the hub client keeps it: ``mcgyvr rig rungs sync`` writes
them into each rung it keeps, as ``busy_answers`` (an HTTP status and an error
code each, :data:`mcgyvr.rig.rungs.BUSY`), and the runner reads them off the
rung's endpoint. An answer the rung names is a full rung
(:class:`~mcgyvr.capacity.SlotUnavailableError`); any other is the error it
was, the hub's old ones included.

A ``relief.yaml`` written before a sync wrote ``busy_answers`` has none, and
behaves exactly as before: for one release the runner falls back to the set it
held (:data:`mcgyvr.runner.RELIEF_UNAVAILABLE`), which is the set a sync now
writes, so re-syncing changes nothing either.

Every server here is a loopback one this test starts.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.capacity import Capacity, SlotUnavailableError
from mcgyvr.config import ConfigSchemaError, parse
from mcgyvr.pool import source_map
from mcgyvr.runner import (
    BackendError,
    ModelUnplacedError,
    ReliefUnavailableError,
    Request,
    RunnerError,
    dispatch,
)
from tests.test_a_relief_rung_that_cannot_take_the_request_now_is_full import (
    HOST_AWAY,
    KEY,
    NOT_SERVED_YET,
    RIDE,
    RUNG_ID,
    STALE,
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

#: Every kind of answer a relief rung was read by before ``busy_answers``, with
#: what a dispatch ended as on ``main`` then: full on the three, and each other
#: its own error.
BEFORE = [
    (NOT_SERVED_YET, ReliefUnavailableError),
    (HOST_AWAY, ReliefUnavailableError),
    (STALE, ReliefUnavailableError),
    (error(503, "pool_unavailable"), BackendError),
    (error(503, "model_unplaced"), ModelUnplacedError),
    (error(401, "invalid_api_key"), BackendError),
    (error(503, "busy"), BackendError),
    ((500, b"{}"), BackendError),
]
BEFORE_IDS = [
    "503-not-served-yet",
    "503-host-away",
    "404-stale",
    "503-other",
    "503-unplaced",
    "401",
    "503-busy",
    "500",
]


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


# --- an old relief.yaml behaves exactly as before ------------------------------


@pytest.mark.parametrize(("answer", "ended_as"), BEFORE, ids=BEFORE_IDS)
def test_an_old_relief_yaml_is_read_as_before_and_as_a_sync_now_writes_it(
    tmp_path: Path, answer: tuple[int, bytes], ended_as: type[Exception]
) -> None:
    _, old = ask(answer, None, tmp_path / "old")
    _, synced = ask(answer, what_a_sync_writes(), tmp_path / "synced")

    assert type(old) is ended_as, old
    assert type(synced) is ended_as, synced


def test_the_fallback_for_an_old_file_is_the_set_a_sync_writes() -> None:
    from mcgyvr import runner
    from mcgyvr.rig import rungs

    assert frozenset(rungs.BUSY) == runner.RELIEF_UNAVAILABLE


#: The last release an old ``relief.yaml`` is read with the runner's fallback.
FALLBACK_LAST_RELEASE = (0, 4, 0)


def release_of(version: str) -> tuple[int, ...]:
    """The release numbers a version starts with: ``0.3.1.dev88+g1`` is
    ``(0, 3, 1)``."""
    found = re.match(r"\d+(?:\.\d+)*", version)
    assert found, version
    return tuple(int(part) for part in found.group().split("."))


def test_the_fallback_is_gone_after_the_release_it_was_kept_for() -> None:
    """Past 0.4.0, delete ``runner.RELIEF_UNAVAILABLE`` and its use, move its
    literal into ``rig/rungs.py`` as ``BUSY``, and delete this test with the
    old-file tests above."""
    import mcgyvr
    from mcgyvr import runner

    past = release_of(mcgyvr.__version__) > FALLBACK_LAST_RELEASE
    assert not (past and hasattr(runner, "RELIEF_UNAVAILABLE")), (
        f"mcgyvr {mcgyvr.__version__} is past 0.4.0, the one release an old "
        "relief.yaml was read with runner.RELIEF_UNAVAILABLE: delete it"
    )


@pytest.mark.parametrize(
    ("version", "release"),
    [
        ("0.3.1.dev88+gcd05b5ec", (0, 3, 1)),
        ("0.4.0", (0, 4, 0)),
        ("0.4.1.dev1", (0, 4, 1)),
    ],
)
def test_a_version_is_read_by_its_release(
    version: str, release: tuple[int, ...]
) -> None:
    assert release_of(version) == release
    assert (release > FALLBACK_LAST_RELEASE) == version.startswith("0.4.1")


def test_an_old_relief_yaml_loads_with_no_busy_answers() -> None:
    config = parse(ladder("http://127.0.0.1:9/v1", None))

    assert config.relief[RIDE].busy_answers is None


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
