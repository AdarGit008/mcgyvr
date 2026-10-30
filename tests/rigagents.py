"""The rig agent's own side of the hub: a hello, a heartbeat, a backing off."""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Iterator
from typing import Any

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

    def wake(self) -> None:
        pass  # receive never blocks: it moves the clock on

    def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed_with = code
        self.closed = _closed(code, reason)


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


class Report:
    def __init__(self) -> None:
        self.reads = 0

    def __call__(self) -> Any:
        from mcgyvr import hubwire
        from mcgyvr.rig import hardware, protocol

        self.reads += 1
        return hardware.Report(
            machine_id="rig-example",
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
            # What the rig lends of it, which is what its frames carry.
            lent=(
                hubwire.Resource(
                    kind=hubwire.RESOURCE_GPU,
                    index=0,
                    name="Example Card",
                    total_mb=8192,
                    free_mb=self.reads,
                    figure=hubwire.FIGURE_READING,
                    backend="cuda",
                ),
            ),
        )


def _agent(
    plan: list[Any],
    clock: Clock,
    *,
    report: Any = None,
    said: list[str] | None = None,
    on_status: Any = None,
    **more: Any,
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
        # a heartbeat's read in place: the fake clock moves only when the agent
        # waits on its channel, which a read on a thread of its own would race
        aside=lambda job: job(),
        **more,
    )
    return made, channels


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
