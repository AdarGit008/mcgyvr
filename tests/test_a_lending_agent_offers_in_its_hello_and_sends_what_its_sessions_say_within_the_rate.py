"""A lending agent offers in its hello, and sends what its sessions say within the rate.

A rig that lends says so in its hello (roles, runtime, endpoints, models,
running sessions); one that does not says nothing of it. What its sessions
and relays say on their own goes through the outbox, which the agent empties
between reads of its channel, never above its frame rate and without
dropping a frame. The sessions are told when the channel is up, when it is
lost (and the outbox no longer takes frames), and when the agent ends —
however it ends.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from tests.test_a_rig_agent_says_hello_keeps_beating_and_backs_off_when_the_hub_drops import (  # noqa: E501
    Channel,
    Clock,
    Hub,
    Report,
)


def _made(plan: list[Hub], clock: Clock, **hooks: Any) -> tuple[Any, list[Channel]]:
    from mcgyvr.rig import agent, websocket

    channels: list[Channel] = []
    steps = iter(plan)

    def connect() -> Channel:
        step = next(steps, None)
        if step is None:
            raise websocket.HandshakeError("the plan is over", status=401)
        channel = Channel(step, clock)
        channels.append(channel)
        return channel

    made = agent.Agent(
        connect=connect,
        read_hardware=Report(),
        agent_version="0.1.0",
        clock=clock,
        wall=clock,
        wait=clock.wait,
        draw=lambda: 1.0,
        say=lambda line: None,
        **hooks,
    )
    return made, channels


def _offer() -> Any:
    from mcgyvr.rig import protocol

    return protocol.Offer(
        roles=("worker",),
        runtime="engine:rpc",
        endpoints=(("192.0.2.10", 51820, "lan"),),
        models=(),
        sessions=("s1",),
    )


def test_the_hello_carries_the_offer_and_a_rig_that_lends_nothing_says_nothing() -> (
    None
):
    clock = Clock()
    agent, channels = _made([Hub(beats=1)], clock, offer=_offer)
    agent.run()
    hello = channels[0].sent[0][1]
    assert hello["body"]["capabilities"] == {
        "roles": ["worker"],
        "runtime": "engine:rpc",
    }
    assert hello["body"]["endpoints"] == [
        {"host": "192.0.2.10", "port": 51820, "kind": "lan"}
    ]
    assert hello["body"]["sessions"] == ["s1"]

    clock = Clock()
    agent, channels = _made([Hub(beats=1)], clock, offer=lambda: None)
    agent.run()
    body = channels[0].sent[0][1]["body"]
    assert not {"capabilities", "endpoints", "models", "sessions"} & set(body)


def test_what_the_sessions_say_goes_out_within_the_rate_and_none_is_dropped() -> None:
    from mcgyvr.rig import agent as rig_agent
    from mcgyvr.rig import outbox, sessionwire

    clock = Clock()
    box = outbox.Outbox(capacity=500)
    told: list[str] = []

    def online() -> None:
        told.append("online")
        for i in range(300):
            assert box.put(
                sessionwire.session_status(None, session_id=f"s{i}", state="ready")
            )

    agent, channels = _made(
        [Hub(interval=15, beats=2)],
        clock,
        outbox=box,
        on_online=online,
        on_offline=lambda: told.append("offline"),
        on_exit=lambda: told.append("exit"),
    )
    agent.run()
    sent = channels[0].sent
    statuses = [m for _, m in sent if m["type"] == "session_status"]
    assert [m["body"]["session_id"] for m in statuses] == [f"s{i}" for i in range(300)]
    per_second = Counter(int(t) for t, _ in sent)
    assert max(per_second.values()) <= rig_agent.FRAMES_PER_SECOND
    assert [m["type"] for _, m in sent].count("heartbeat") == 2
    assert told == ["online", "offline", "exit"]
    assert not box.put("late")  # the channel is gone: nothing is queued for it


def test_the_sessions_are_told_of_the_agents_end_when_it_is_stopped() -> None:
    from mcgyvr.rig import outbox

    clock = Clock()
    told: list[str] = []
    made: list[Any] = []

    def online() -> None:
        told.append("online")
        made[0].stop()

    agent, _ = _made(
        [Hub(interval=15)],
        clock,
        outbox=outbox.Outbox(),
        on_online=online,
        on_offline=lambda: told.append("offline"),
        on_exit=lambda: told.append("exit"),
    )
    made.append(agent)
    ended = agent.run()
    assert ended.stopped
    assert told == ["online", "offline", "exit"]
