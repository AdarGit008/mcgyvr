"""A rig agent says hello, keeps beating, and backs off when the hub drops it.

The agent reads the machine before it connects, says hello with that reading
first, and waits for the hub's ack, which sets the heartbeat interval. Each
heartbeat carries a fresh reading. A channel that drops, times out, or is
throttled is reopened after a backoff that grows to a cap and starts over once
a session has held; a hub that refuses the token, revokes it, binds it to
another machine, or hands the rig to a newer agent ends the agent instead,
since asking again would be refused again. A hub that stops acking is given
up on. Whatever the hub floods the agent with, the agent answers within a
rate the hub allows and keeps beating. Asked to stop, it closes the channel
cleanly.
"""

from __future__ import annotations

import itertools
import json
from collections import deque
from collections.abc import Iterator
from typing import Any

import pytest

from tests import rig_schema


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.waits: list[float] = []

    def __call__(self) -> float:
        return self.now

    def wait(self, seconds: float) -> bool:
        self.waits.append(seconds)
        self.now += seconds
        return False


def _closed(code: int, reason: str = "") -> Any:
    from mcgyvr.rig.websocket import ClosedError

    return ClosedError(code, reason, by_peer=True)


def _frame(kind: str, re: str | None = None, **body: Any) -> str:
    from mcgyvr.rig import protocol

    message: dict[str, Any] = {
        "v": 1,
        "type": kind,
        "id": protocol.new_id(),
        "body": body,
    }
    if re is not None:
        message["re"] = re
    return json.dumps(message)


class Hub:
    """One connection's hub: acks as told, then closes as told."""

    def __init__(
        self,
        *,
        interval: int | None = 15,
        ack_hello: bool = True,
        ack_beats: bool = True,
        beats: int | None = None,
        end: Any = None,
        error: str | None = None,
        flood: int = 0,
        lasts: float | None = None,
    ) -> None:
        self.interval = interval
        self.ack_hello = ack_hello
        self.ack_beats = ack_beats
        self.beats = beats
        self.end = end if end is not None else _closed(1006, "dropped")
        self.error = error
        self.flood = flood
        self.lasts = lasts
        self.received: list[dict[str, Any]] = []
        self.started: float | None = None

    def answer(self, message: dict[str, Any], channel: Channel) -> list[Any]:
        self.received.append(message)
        if message["type"] == "hello":
            self.started = channel.clock.now
            if not self.ack_hello:
                return []
            out: list[Any] = [
                _frame(
                    "ack",
                    message["id"],
                    rig_id="r-1",
                    heartbeat_interval_s=self.interval,
                )
                if self.interval is not None
                else _frame("ack", message["id"], rig_id="r-1")
            ]
            out += [_frame("start_worker", model="x") for _ in range(self.flood)]
            if self.beats == 0:
                out += self._ending(message)
            return out
        if message["type"] == "heartbeat":
            beats = sum(1 for m in self.received if m["type"] == "heartbeat")
            out = [_frame("ack", message["id"])] if self.ack_beats else []
            if self.beats is not None and beats >= self.beats:
                out += self._ending(message)
            return out
        return []

    def _ending(self, message: dict[str, Any]) -> list[Any]:
        out: list[Any] = []
        if self.error:
            out.append(_frame("error", message["id"], code=self.error, message="no"))
        out.append(self.end)
        return out

    def idle(self, channel: Channel) -> Any:
        if (
            self.lasts is not None
            and self.started is not None
            and channel.clock.now - self.started >= self.lasts
        ):
            return self.end
        return None


class Channel:
    def __init__(self, hub: Hub, clock: Clock) -> None:
        self.hub = hub
        self.clock = clock
        self.sent: list[tuple[float, dict[str, Any]]] = []
        self.inbox: deque[Any] = deque()
        self.closed: Any = None
        self.closed_with: int | None = None

    def send_text(self, text: str) -> None:
        if self.closed is not None:
            raise self.closed
        message = json.loads(text)
        rig_schema.validate(message, rig_schema.load(), "#/$defs/AgentMessage")
        self.sent.append((self.clock.now, message))
        self.inbox.extend(self.hub.answer(message, self))

    def receive(self, timeout: float) -> str | bytes | None:
        if self.closed is not None:
            raise self.closed
        if not self.inbox:
            ending = self.hub.idle(self)
            if ending is not None:
                self.inbox.append(ending)
        if self.inbox:
            item = self.inbox.popleft()
            if isinstance(item, Exception):
                self.closed = item
                raise item
            assert isinstance(item, str)
            return item
        self.clock.now += max(timeout, 0.001)
        return None

    def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed_with = code
        self.closed = _closed(code, reason)


class Report:
    def __init__(self) -> None:
        self.reads = 0

    def __call__(self) -> Any:
        from mcgyvr.rig import hardware, protocol

        self.reads += 1
        return hardware.Report(
            machine_id="mch-example",
            ram_total_mb=65536,
            ram_free_mb=1000 + self.reads,
            cards=(
                protocol.CardReport(
                    index=0,
                    name="Example Card",
                    vram_total_mb=8192,
                    vram_free_mb=self.reads,
                ),
            ),
            notes=(),
        )


def _agent(
    plan: list[Any],
    clock: Clock,
    *,
    report: Any = None,
    said: list[str] | None = None,
    on_status: Any = None,
) -> tuple[Any, list[Channel]]:
    from mcgyvr.rig import agent, websocket

    channels: list[Channel] = []
    steps: Iterator[Any] = iter(plan)

    def connect() -> Channel:
        step = next(steps, None)
        if step is None:
            raise websocket.HandshakeError("the plan is over", status=401)
        if isinstance(step, Exception):
            raise step
        channel = Channel(step, clock)
        channels.append(channel)
        return channel

    made = agent.Agent(
        connect=connect,
        read_hardware=report or Report(),
        agent_version="0.1.0",
        clock=clock,
        wall=clock,
        wait=clock.wait,
        on_status=on_status,
        draw=lambda: 1.0,
        say=(said.append if said is not None else lambda line: None),
    )
    return made, channels


def test_hello_is_first_with_the_reading_and_each_heartbeat_reads_again() -> None:
    clock = Clock()
    report = Report()
    hub = Hub(interval=15, beats=3)
    agent, channels = _agent([hub], clock, report=report)
    ended = agent.run()
    assert not ended.stopped
    sent = [m for _, m in channels[0].sent]
    assert [m["type"] for m in sent] == ["hello", "heartbeat", "heartbeat", "heartbeat"]
    assert sent[0]["body"]["machine_id"] == "mch-example"
    assert sent[0]["body"]["agent_version"] == "0.1.0"
    assert sent[0]["body"]["cards"][0]["vram_free_mb"] == 1
    assert [m["body"]["cards"][0]["vram_free_mb"] for m in sent[1:]] == [2, 3, 4]
    times = [t for t, _ in channels[0].sent]
    assert [round(b - a) for a, b in itertools.pairwise(times)] == [
        15,
        15,
        15,
    ]


def test_a_hello_ack_without_an_interval_beats_at_the_default() -> None:
    from mcgyvr.rig import agent as rig_agent

    clock = Clock()
    agent, channels = _agent([Hub(interval=None, beats=2)], clock)
    agent.run()
    times = [t for t, _ in channels[0].sent]
    assert round(times[2] - times[1]) == rig_agent.DEFAULT_HEARTBEAT_S


@pytest.mark.parametrize(
    ("ending", "error"),
    [
        (_closed(1006), None),
        (_closed(4008, "heartbeat missed"), "timeout"),
        (_closed(1008, "too many frames"), "rate_limited"),
        (_closed(1011), None),
        (_closed(1008), "some_code_from_later"),
    ],
)
def test_a_channel_that_drops_is_reopened(ending: Any, error: str | None) -> None:
    clock = Clock()
    plan = [Hub(beats=1, end=ending, error=error), Hub(beats=1)]
    agent, channels = _agent(plan, clock)
    agent.run()
    assert len(channels) == 2
    assert channels[1].sent[0][1]["type"] == "hello"


@pytest.mark.parametrize(
    ("step", "words"),
    [
        ("handshake 403", "refused"),
        ("handshake 401", "refused"),
        ("handshake 404", "agent channel"),
        ("revoked", "revoked"),
        ("superseded", "another agent"),
        ("machine_mismatch", "another machine"),
        ("unsupported_version", "update"),
    ],
)
def test_a_refusal_ends_the_agent_without_asking_again(step: str, words: str) -> None:
    from mcgyvr.rig import websocket

    clock = Clock()
    plan: list[Any]
    if step.startswith("handshake"):
        plan = [websocket.HandshakeError("no", status=int(step.split()[1])), Hub()]
    elif step == "revoked":
        plan = [Hub(beats=1, end=_closed(4001), error="revoked"), Hub()]
    elif step == "superseded":
        plan = [Hub(beats=1, end=_closed(4009), error="superseded"), Hub()]
    else:
        plan = [Hub(beats=0, end=_closed(1008), error=step), Hub()]
    said: list[str] = []
    agent, channels = _agent(plan, clock, said=said)
    ended = agent.run()
    assert not ended.stopped
    assert words in ended.why
    assert len(channels) <= 1
    assert not clock.waits


def test_the_backoff_grows_to_its_cap_and_starts_over_after_a_steady_session() -> None:
    from mcgyvr.rig import agent as rig_agent
    from mcgyvr.rig import websocket

    clock = Clock()
    backoff = rig_agent.Backoff()
    unreachable = [websocket.HandshakeError("down", status=503) for _ in range(9)]
    steady = Hub(lasts=backoff.steady_s + 1)
    plan = [*unreachable, steady, websocket.HandshakeError("down", status=None)]
    agent, _ = _agent(plan, clock)
    agent.run()
    waits = clock.waits
    expected = [
        min(backoff.cap_s, backoff.first_s * backoff.factor**n) for n in range(9)
    ]
    assert waits[:9] == pytest.approx(expected)
    assert max(waits) <= backoff.cap_s
    assert waits[9] == pytest.approx(backoff.first_s)


def test_a_session_that_does_not_hold_keeps_the_backoff_growing() -> None:
    from mcgyvr.rig import agent as rig_agent

    clock = Clock()
    backoff = rig_agent.Backoff()
    plan = [Hub(beats=0), Hub(beats=0), Hub(beats=0)]
    agent, _ = _agent(plan, clock)
    agent.run()
    assert clock.waits[:3] == pytest.approx(
        [backoff.first_s, backoff.first_s * 2, backoff.first_s * 4]
    )


def test_a_hub_that_stops_acking_is_given_up_on_and_reopened() -> None:
    from mcgyvr.rig import agent as rig_agent

    clock = Clock()
    plan = [Hub(ack_beats=False), Hub(beats=1)]
    agent, channels = _agent(plan, clock)
    agent.run()
    assert len(channels) == 2
    assert channels[0].closed_with is not None
    beats = [m for _, m in channels[0].sent if m["type"] == "heartbeat"]
    assert len(beats) == rig_agent.MISSED_ACKS


def test_a_hello_that_is_never_acked_is_given_up_on() -> None:
    clock = Clock()
    plan = [Hub(ack_hello=False), Hub(beats=1)]
    agent, channels = _agent(plan, clock)
    agent.run()
    assert len(channels) == 2
    assert [m["type"] for _, m in channels[0].sent] == ["hello"]


def test_a_flood_is_answered_within_the_rate_and_the_agent_keeps_beating() -> None:
    from mcgyvr.rig import agent as rig_agent
    from mcgyvr.rig import protocol

    clock = Clock()
    agent, channels = _agent([Hub(beats=2, flood=200)], clock)
    agent.run()
    sent = channels[0].sent
    replies = [(t, m) for t, m in sent if m["type"] == "error"]
    assert replies and all(m["body"]["code"] == "unsupported_type" for _, m in replies)
    for t, _ in sent:
        in_window = [u for u, _ in sent if t <= u < t + 1.0]
        assert len(in_window) <= rig_agent.FRAMES_PER_SECOND
    assert rig_agent.FRAMES_PER_SECOND < protocol.MAX_FRAMES_PER_SECOND
    assert sum(1 for _, m in sent if m["type"] == "heartbeat") == 2


def test_a_machine_that_cannot_be_read_is_not_said_hello_for() -> None:
    from mcgyvr.rig import hardware

    clock = Clock()
    reads: list[int] = []

    def unreadable() -> Any:
        reads.append(1)
        if len(reads) < 3:
            raise hardware.HardwareError("this machine has no short id: a card")
        return Report()()

    said: list[str] = []
    agent, channels = _agent([Hub(beats=1)], clock, report=unreadable, said=said)
    agent.run()
    assert len(channels) == 1
    assert len(clock.waits) >= 2
    assert any("no short id" in line for line in said)


def test_a_heartbeat_whose_reading_fails_still_beats() -> None:
    from mcgyvr.rig import hardware

    clock = Clock()
    good = Report()
    calls: list[int] = []

    def flaky() -> Any:
        calls.append(1)
        if len(calls) == 2:
            raise hardware.HardwareError("the machine reader exited 1")
        return good()

    agent, channels = _agent([Hub(beats=2)], clock, report=flaky)
    agent.run()
    beats = [m for _, m in channels[0].sent if m["type"] == "heartbeat"]
    assert len(beats) == 2
    assert beats[0]["body"] == {"cards": []}


def test_asked_to_stop_it_closes_the_channel_cleanly() -> None:
    clock = Clock()
    hub = Hub()
    agent, channels = _agent([hub], clock)

    def stop_after_two_beats(message: dict[str, Any], channel: Channel) -> list[Any]:
        out = Hub.answer(hub, message, channel)
        if sum(1 for m in hub.received if m["type"] == "heartbeat") == 2:
            agent.stop()
        return out

    hub.answer = stop_after_two_beats  # type: ignore[method-assign]
    ended = agent.run()
    assert ended.stopped
    assert channels[0].closed_with == 1000


def test_what_the_hub_says_is_shown_printable_and_short() -> None:
    from mcgyvr.rig import websocket

    clock = Clock()
    said: list[str] = []
    plan = [Hub(beats=1, end=_closed(4001, "x\x1b[31m" + "y" * 500), error="revoked")]
    agent, _ = _agent(plan, clock, said=said)
    ended = agent.run()
    for line in [*said, ended.why]:
        assert "\x1b" not in line and "y" * 300 not in line
    assert isinstance(websocket.ClosedError, type)


def test_each_ack_is_told_when_it_arrives_not_a_beat_later() -> None:
    from mcgyvr.rig import agent as rig_agent

    clock = Clock()
    told: list[tuple[float, Any]] = []
    plan = [Hub(interval=15, beats=2)]
    made, _ = _agent(
        plan, clock, on_status=lambda status: told.append((clock.now, status))
    )
    made.run()
    acked = [(at, s.last_ack_at) for at, s in told if s.connected]
    assert [round(at) for at, _ in acked] == [0, 15, 30]
    assert all(at == last for at, last in acked)
    assert told[-1][1] == rig_agent.Status(
        connected=False, rig_id=None, heartbeat_s=None, last_ack_at=None
    )
