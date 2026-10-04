"""A bound jev unit is resident: it is never slept and never woken.

Owner ruling. The Jev unit is an opt-in at setup, dedicated VRAM that answers
every typed decision at once; a decision that had to wait out a wake, or a
card that could be slept from under it, would make every typed question a
gamble. So the unit — and any card that holds it — is excluded from every
sleep and wake path unconditionally: what the ladder manager may sleep or
wake, the manager's switches, the door's own verbs, and the waker a dispatch
goes through. A typed decision never wakes anything first. Without a
``jev.unit`` nothing here changes.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import wake as wakelib
from mcgyvr.config import Config, parse
from mcgyvr.decision import Decision
from mcgyvr.drive import _through
from mcgyvr.ladder_manager import sleepable_rungs
from mcgyvr.runner import RefusedConnectionError
from mcgyvr.verify import Reviewer

HOST = "box.invalid"
OTHER = "box.test"


def _config(compose_dir: Path, *, jev: str | None) -> Config:
    jev_block = f"jev:\n  unit: {jev}\n" if jev else ""
    return parse(
        f"""
units:
  small:
    address: "http://{HOST}:8080"
    model: small-7b
    rig: {HOST}
    window: 4096
  big:
    address: "http://{OTHER}:8080"
    model: big-30b
    rig: {OTHER}
    window: 4096
  judge:
    address: "http://{HOST}:8081"
    model: judge-4b
    rig: {HOST}
    window: 4096
ladder:
- small
- big
{jev_block}serving:
  compose_dir: {compose_dir}
  enable_sleep_wake: true
"""
    )


@pytest.fixture
def compose_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "compose"
    folder.mkdir()
    for host in (HOST, OTHER):
        (folder / f"compose.{host}.yml").write_text("services: {}\n", encoding="utf-8")
    return folder


def test_without_a_jev_unit_every_card_with_one_spec_is_wakeable(
    compose_dir: Path,
) -> None:
    config = _config(compose_dir, jev=None)
    assert wakelib.wakeable_rungs(config) == ("small", "big")
    assert sleepable_rungs(config) == ("small", "big")


def test_the_card_holding_the_jev_unit_is_neither_wakeable_nor_sleepable(
    compose_dir: Path,
) -> None:
    config = _config(compose_dir, jev="judge")
    # `judge` is off the ladder but shares `rig` with `small`: that card goes
    # with it, whole, and the other rig's card is untouched.
    assert wakelib.resident_units(config) == frozenset({"judge"})
    assert wakelib.wakeable_rungs(config) == ("big",)
    assert sleepable_rungs(config) == ("big",)


def test_the_door_refuses_to_sleep_or_wake_a_card_holding_the_jev_unit(
    compose_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(compose_dir, jev="judge")
    ran: list[Any] = []
    monkeypatch.setattr(wakelib, "_run_door", lambda *a, **k: ran.append(a))
    with pytest.raises(wakelib.WakeError, match="judge"):
        wakelib.sleep(config, HOST)
    with pytest.raises(wakelib.WakeError, match="judge"):
        wakelib.wake(config, HOST)
    assert ran == []


def test_the_managers_switches_decline_the_jev_card_without_touching_the_door(
    compose_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.capacity import Capacity

    config = _config(compose_dir, jev="judge")
    ran: list[Any] = []
    monkeypatch.setattr(wakelib, "_run_door", lambda *a, **k: ran.append(a))
    monkeypatch.setattr(wakelib, "for_config", lambda c: ran.append("waker"))
    switches = wakelib.CardSwitches(config, Capacity.of(config))
    assert switches.sleep("small") is False
    assert switches.wake("small") is False
    assert switches.sleep("judge") is False
    assert switches.wake("judge") is False
    assert ran == []


def test_a_dispatch_to_the_jev_card_is_never_a_wake(
    compose_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(compose_dir, jev="judge")
    waker = wakelib.Waker(config)
    woke: list[str] = []

    def fake_wake(rung: str, **_: object) -> bool:
        woke.append(rung)
        return True

    monkeypatch.setattr(waker, "wake_for", fake_wake)

    def refused() -> str:
        raise RefusedConnectionError("port closed")

    with pytest.raises(RefusedConnectionError):
        waker.dispatching("judge", refused)
    with pytest.raises(RefusedConnectionError):
        waker.dispatching("small", refused)
    assert woke == []
    # The other rig's card still wakes on a refusal, as before.
    answers: Iterator[RefusedConnectionError | str] = iter(
        [RefusedConnectionError("closed"), "ok"]
    )

    def flaky() -> str:
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    assert waker.dispatching("big", flaky) == "ok"
    assert woke == ["big"]


def test_a_typed_decision_goes_around_the_waker_when_a_jev_unit_is_bound(
    compose_dir: Path,
) -> None:
    config = _config(compose_dir, jev="judge")
    waker = wakelib.Waker(config)
    seen: list[str] = []

    def decide(state: Any) -> Decision:
        seen.append("decided")
        return Decision(answers={})

    def ask(prompt: str) -> str:
        seen.append("asked")
        return "fine"

    reviewer = Reviewer(
        model="big-30b", ask=ask, decide=decide, jev=None, where="big", unit="big"
    )
    routed = _through(waker, reviewer, jev_resident=True)
    assert routed.decide is decide  # untouched: Jev is resident, nothing to wake
    assert routed.ask is not ask  # the prose ask still goes through the waker
    unbound = _through(waker, reviewer, jev_resident=False)
    assert unbound.decide is not decide  # as before, without a jev unit
