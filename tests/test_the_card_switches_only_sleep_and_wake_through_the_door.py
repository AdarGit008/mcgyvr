"""The card switches sleep and wake through the door a person's ``serve`` uses.

The promises:

* **One door, a fresh waker.** :class:`~mcgyvr.wake.CardSwitches` wakes a card
  by the same ``serve up`` a refused dispatch runs, and wakes it again when
  asked again later: it may wake a card it has since slept, so it never reuses
  a waker's one-wake-per-run memory.
* **Sleep drains first, and a busy card is not slept.** A sleep takes every
  slot of the card before the door's ``down``; a dispatch still running makes
  it ``False`` and runs no door.
* **The switch gates the switches, not the person.** With
  ``serving.enable_sleep_wake`` off neither verb spawns anything.
* **A card goes whole.** ``room_for`` is always empty and ``card_of`` names
  every rung the card serves.

Everything here is a fake: the door is substituted at ``mcgyvr.wake.spawn_door``;
no network is reached.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import Config, parse
from tests import livejournal as lj
from tests.doors import door_log

FAST = "local_fast"
BIG_A = "local_big_a"
BIG_B = "local_big_b"
API = "api_big"

FAST_HOST = "fast-box.example"
BIG_HOST = "big-box.example"


def ladder_text(
    compose_dir: Path | None,
    *,
    sleep_wake: bool = True,
    timeout_s: float | None = None,
    api: bool = False,
    engine: str | None = None,
) -> str:
    """A fast rung, and two rungs sharing one big card (served by ``engine``)."""
    timeout = "" if timeout_s is None else f"    request_timeout_s: {timeout_s}\n"
    if engine is not None:
        timeout += f"    engine: {engine}\n"
    serving = ""
    if compose_dir is not None:
        serving = (
            "serving:\n"
            f"  compose_dir: {compose_dir}\n"
            f"  enable_sleep_wake: {'true' if sleep_wake else 'false'}\n"
        )
    text = (
        "units:\n"
        f"  {FAST}:\n"
        f"    address: http://{FAST_HOST}:8000\n"
        "    model: small-coder\n"
        "    rig: fast-rig\n"
        "    width: 2\n"
        f"  {BIG_A}:\n"
        f"    address: http://{BIG_HOST}:8001\n"
        "    model: large-coder\n"
        "    rig: big-rig-a\n"
        "    width: 2\n" + timeout + f"  {BIG_B}:\n"
        f"    address: http://{BIG_HOST}:8002\n"
        "    model: large-coder-two\n"
        "    rig: big-rig-b\n"
        "    width: 2\n" + timeout
    )
    names = [FAST, BIG_A, BIG_B]
    if api:
        text += (
            f"  {API}:\n"
            "    address: https://api.example.com/v1\n"
            "    model: vendor-large\n"
            "    rig: vendor\n"
            "    width: 4\n"
            "    api_key_env: EXAMPLE_API_KEY\n"
        )
        names.append(API)
    text += "ladder:\n" + "".join(f"- {n}\n" for n in names)
    return text + serving


def write_spec(tmp_path: Path) -> Path:
    """One launch spec for the big card, as ``emit`` would write it."""
    from mcgyvr.serving import COMPOSE_PREFIX, COMPOSE_SUFFIX

    where = tmp_path / "specs"
    where.mkdir(exist_ok=True)
    (where / f"{COMPOSE_PREFIX}{BIG_HOST}{COMPOSE_SUFFIX}").write_text(
        "services:\n  big:\n    image: example/server:1\n", encoding="utf-8"
    )
    return where


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A HOME and a rendezvous directory nobody else writes to."""
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    (tmp_path / "rendezvous").mkdir(exist_ok=True)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "rendezvous"))
    return tmp_path / "home"


def switches_for(config: Config) -> Any:
    """The manager's switches, over a capacity that can see who is waiting."""
    from mcgyvr.capacity import Capacity
    from mcgyvr.pressure import Gauge
    from mcgyvr.wake import CardSwitches

    return CardSwitches(config, Capacity.of(config, gauge=Gauge()))


def verb(argv: list[str]) -> str:
    return argv[argv.index("serve") + 1]


# --- the door ----------------------------------------------------------------


def test_a_wake_runs_the_door_up_for_the_card_and_runs_it_again_when_asked_again(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each wake is a fresh waker, so a card slept in between is woken again."""
    specs = write_spec(tmp_path)
    config = parse(ladder_text(specs))
    spawned = door_log(monkeypatch)
    switches = switches_for(config)

    first = switches.wake(BIG_A)
    second = switches.wake(BIG_A)

    assert first is True and second is True
    assert [verb(argv) for argv in spawned] == ["up", "up"], spawned
    for argv in spawned:
        assert BIG_HOST in argv, argv
        assert str(specs / f"compose.{BIG_HOST}.yml") in argv, argv


def test_a_sleep_drains_the_card_and_then_runs_the_door_down(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    specs = write_spec(tmp_path)
    config = parse(ladder_text(specs))
    spawned = door_log(monkeypatch)

    slept = switches_for(config).sleep(BIG_A)

    assert slept is True
    assert [verb(argv) for argv in spawned] == ["down"], spawned
    assert BIG_HOST in spawned[0], spawned


def test_a_sleep_with_a_dispatch_still_running_is_not_done_and_runs_no_door(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A slot held by another holder is a request in flight: not now."""
    from mcgyvr.capacity import Capacity

    specs = write_spec(tmp_path)
    config = parse(ladder_text(specs, timeout_s=0.2))
    spawned = door_log(monkeypatch)
    holder = Capacity.of(config)

    with holder.hold(BIG_B):
        slept = switches_for(config).sleep(BIG_A)

    assert slept is False
    assert spawned == [], spawned


def test_a_sleep_with_a_dispatch_queued_for_the_card_is_not_done_and_runs_no_door(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dispatch that queued while the drain held the slots would get one the
    moment the card went down, be refused, and wake the card again: down and up
    back to back, with the task waiting through both."""
    from mcgyvr.capacity import Capacity, _slot_stem, _waiting_key
    from mcgyvr.pressure import Gauge
    from mcgyvr.wake import CardSwitches

    specs = write_spec(tmp_path)
    config = parse(ladder_text(specs))
    spawned = door_log(monkeypatch)
    gauge = Gauge()
    switches = CardSwitches(config, Capacity.of(config, gauge=gauge))
    queued = _waiting_key(_slot_stem(f"http://{BIG_HOST}:8002"))

    with gauge.present(queued):
        slept = switches.sleep(BIG_A)

    assert slept is False
    assert spawned == [], spawned


def test_a_sleep_that_cannot_see_who_is_waiting_is_not_done(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No gauge is no reading, and no reading is not an empty queue."""
    from mcgyvr.capacity import Capacity
    from mcgyvr.wake import CardSwitches

    specs = write_spec(tmp_path)
    config = parse(ladder_text(specs))
    spawned = door_log(monkeypatch)

    assert CardSwitches(config, Capacity.of(config)).sleep(BIG_A) is False
    assert spawned == [], spawned


def test_a_door_that_fails_is_a_sleep_that_did_not_happen(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mcgyvr.wake as wake

    specs = write_spec(tmp_path)
    config = parse(ladder_text(specs))
    monkeypatch.setattr(wake, "spawn_door", lambda argv, **_: 1)

    switches = switches_for(config)

    assert switches.sleep(BIG_A) is False
    assert switches.wake(BIG_A) is False


# --- a vLLM card keeps its process -------------------------------------------


def door_by_verb(
    monkeypatch: pytest.MonkeyPatch, codes: dict[str, int] | None = None
) -> list[str]:
    """The door, answering each verb with its code in ``codes`` (0 otherwise)."""
    import mcgyvr.wake as wake

    log: list[str] = []

    def spawn(argv: list[str], **_: Any) -> int:
        log.append(verb(argv))
        return (codes or {}).get(verb(argv), 0)

    monkeypatch.setattr(wake, "spawn_door", spawn)
    return log


def test_a_vllm_card_is_put_to_sleep_with_its_process_kept(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Level 2 drops the weights and keeps the server; a cold start is not the cost."""
    config = parse(ladder_text(write_spec(tmp_path), engine="vllm"))
    doors = door_by_verb(monkeypatch)

    assert switches_for(config).sleep(BIG_A) is True
    assert doors == ["sleep"], "a vLLM card's containers were stopped"


def test_a_vllm_card_with_no_sleep_route_falls_back_to_stopping_its_containers(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.serving.gatelib import NO_SLEEP_ROUTE

    config = parse(ladder_text(write_spec(tmp_path), engine="vllm"))
    doors = door_by_verb(monkeypatch, {"sleep": NO_SLEEP_ROUTE})

    assert switches_for(config).sleep(BIG_A) is True
    assert doors == ["sleep", "down"]


def test_a_llamacpp_card_has_no_sleep_to_ask_for_and_is_stopped(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = parse(ladder_text(write_spec(tmp_path)))
    doors = door_by_verb(monkeypatch)

    assert switches_for(config).sleep(BIG_A) is True
    assert doors == ["down"]


def test_a_card_slept_with_its_process_kept_is_woken_by_its_wake_route(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``serve up`` would be refused on a busy rig, and would start nothing new."""
    config = parse(ladder_text(write_spec(tmp_path), engine="vllm"))
    doors = door_by_verb(monkeypatch)
    switches = switches_for(config)

    assert switches.sleep(BIG_A) is True
    assert switches.wake(BIG_A) is True
    assert switches.wake(BIG_A) is True
    assert doors == ["sleep", "wake", "up"], (
        "once woken, the card is no longer resting, so the next wake is a start"
    )


def test_a_dispatch_to_a_card_slept_with_its_process_kept_wakes_it_before_sending(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A level-2 sleeper answers and then hangs, so it never gives the refusal
    a wake waits for. The card's resting mark is that refusal, read for free."""
    import mcgyvr.wake as wake

    config = parse(ladder_text(write_spec(tmp_path), engine="vllm"))
    doors = door_by_verb(monkeypatch)
    assert switches_for(config).sleep(BIG_A) is True

    order: list[str] = []
    real = wake.spawn_door

    def spawn(argv: list[str], **kwargs: Any) -> int:
        order.append(f"door {verb(argv)}")
        return real(argv, **kwargs)

    monkeypatch.setattr(wake, "spawn_door", spawn)
    waker = wake.for_config(config)
    assert waker is not None

    def send() -> str:
        order.append("send")
        return "answer"

    assert waker.dispatching(BIG_B, send) == "answer"
    assert order == ["door wake", "send"], order
    assert doors == ["sleep", "wake"]


# --- the switch --------------------------------------------------------------


def test_with_the_switch_off_neither_verb_spawns_anything(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    specs = write_spec(tmp_path)
    config = parse(ladder_text(specs, sleep_wake=False))
    spawned = door_log(monkeypatch)
    switches = switches_for(config)

    assert switches.wake(BIG_A) is False
    assert switches.sleep(BIG_A) is False
    assert spawned == [], spawned


def test_a_rung_whose_card_holds_no_single_launch_spec_is_neither_woken_nor_slept(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    specs = write_spec(tmp_path)
    config = parse(ladder_text(specs))
    spawned = door_log(monkeypatch)
    switches = switches_for(config)

    assert switches.wake(FAST) is False
    assert switches.sleep(FAST) is False
    assert spawned == [], spawned


# --- a card goes whole -------------------------------------------------------


def test_no_unit_needs_room_made_because_a_card_goes_whole(
    tmp_path: Path, home: Path
) -> None:
    config = parse(ladder_text(write_spec(tmp_path)))
    switches = switches_for(config)

    assert switches.room_for(BIG_A) == ()
    assert switches.room_for(BIG_B) == ()


def test_a_cards_rungs_are_every_rung_the_host_serves(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EXAMPLE_API_KEY", "sk-" + "0" * 12)
    config = parse(ladder_text(write_spec(tmp_path), api=True))
    switches = switches_for(config)

    assert set(switches.card_of(BIG_A)) == {BIG_A, BIG_B}
    assert set(switches.card_of(BIG_B)) == {BIG_A, BIG_B}
    assert switches.card_of(API) == (API,)


def test_the_drain_waits_as_long_as_the_slowest_unit_on_the_card_may_take(
    tmp_path: Path,
) -> None:
    from mcgyvr.serving import cards
    from mcgyvr.wake import drain_timeout

    specs = write_spec(tmp_path)
    stated = parse(ladder_text(specs, timeout_s=7.5))
    unstated = parse(ladder_text(specs))

    assert drain_timeout(stated, cards(stated)[BIG_A]) == 7.5
    assert drain_timeout(unstated, cards(unstated)[BIG_A]) is None
