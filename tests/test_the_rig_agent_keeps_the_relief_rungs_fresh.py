"""The rig agent keeps the relief rungs fresh on its own tick, when it may.

The agent's one periodic tick is its heartbeat. After each heartbeat it is
sent, it tells ``on_beat``; nothing is told for the hello. When the variable
holding the rider's personal hub key is set (``MCGYVR_HUB_API_KEY``), the agent
hands that tick a :class:`~mcgyvr.rig.rungs.Refresher`, which syncs the relief
rungs as ``mcgyvr rig rungs sync`` does:

* at the first beat, and then no sooner than the hub's ``refresh_s`` says it
  re-matches — syncing more often gains nothing;
* off the agent's thread, one sync at a time: a beat never waits on the hub's
  rungs, and a beat while a sync is still going starts none;
* a sync that fails is said (once while it keeps failing the same way) and
  tried again later; it never ends the agent.

With the variable unset, no refresher is made and nothing is asked.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcgyvr.rig import rungs
from tests.test_a_rig_agent_says_hello_keeps_beating_and_backs_off_when_the_hub_drops import (  # noqa: E501
    Clock,
    Hub,
    _agent,
)


def test_the_agent_tells_its_tick_after_each_heartbeat_and_not_for_the_hello() -> None:
    clock = Clock()
    ticks: list[float] = []
    agent, channels = _agent(
        [Hub(interval=15, beats=3)], clock, on_beat=lambda: ticks.append(clock.now)
    )

    agent.run()

    beats = [t for t, m in channels[0].sent if m["type"] == "heartbeat"]
    assert ticks == beats


class Now:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def rides(refresh_s: float = 60.0) -> rungs.Rides:
    return rungs.Rides(ride=True, privacy="p", refresh_s=refresh_s, rungs=())


def refresher(
    sync: Callable[[], rungs.Rides],
    now: Now,
    said: list[str],
    start: Callable[[Callable[[], None]], None] | None = None,
) -> rungs.Refresher:
    return rungs.Refresher(
        sync=sync,
        clock=now,
        say=said.append,
        start=start or (lambda work: work()),
    )


def test_it_syncs_at_the_first_beat_and_then_as_often_as_the_hub_rematches() -> None:
    now, said, synced = Now(), list[str](), list[float]()

    def sync() -> rungs.Rides:
        synced.append(now.now)
        return rides(refresh_s=60)

    tick = refresher(sync, now, said)
    for at in (0, 15, 30, 45, 60, 75, 90, 105, 120):
        now.now = at
        tick.tick()

    assert synced == [0, 60, 120]


def test_a_beat_while_a_sync_is_going_starts_no_other() -> None:
    now, said = Now(), list[str]()
    pending: list[Callable[[], None]] = []
    calls: list[int] = []

    def sync() -> rungs.Rides:
        calls.append(1)
        return rides(refresh_s=1)

    tick = refresher(sync, now, said, start=pending.append)
    tick.tick()
    now.now = 100
    tick.tick()
    assert len(pending) == 1

    pending.pop()()
    now.now = 200
    tick.tick()
    assert len(pending) == 1
    assert calls == [1]


def test_a_failing_sync_is_said_once_retried_later_and_never_raised() -> None:
    now, said = Now(), list[str]()
    tried: list[float] = []

    def sync() -> rungs.Rides:
        tried.append(now.now)
        raise rungs.SyncError("the hub could not be reached")

    tick = refresher(sync, now, said)
    for at in range(0, int(rungs.RETRY_S) * 2 + 1, 15):
        now.now = at
        tick.tick()

    assert tried == [0, rungs.RETRY_S, rungs.RETRY_S * 2]
    assert len([line for line in said if "could not be reached" in line]) == 1


def test_a_refused_answer_is_said_and_retried_too() -> None:
    now, said = Now(), list[str]()

    def sync() -> rungs.Rides:
        raise rungs.HubAnswerError("the hub's answer is refused: width")

    tick = refresher(sync, now, said)
    tick.tick()

    assert any("refused" in line for line in said)


def test_no_refresher_is_made_without_the_key() -> None:
    environ: dict[str, Any] = {}

    assert rungs.refresher_for("https://hub.example.org", environ=environ) is None


def test_with_the_key_a_refresher_is_made_for_the_kept_hub() -> None:
    environ = {rungs.KEY_ENV: "mhu_" + "0" * 16}

    made = rungs.refresher_for("https://hub.example.org", environ=environ)

    assert isinstance(made, rungs.Refresher)
