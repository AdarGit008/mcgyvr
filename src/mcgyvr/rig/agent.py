""

from __future__ import annotations

import random
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from mcgyvr.rig import commands, hardware, protocol, websocket
from mcgyvr.rig.outbox import Outbox

#
#
DEFAULT_HEARTBEAT_S = 15
#
HELLO_ACK_TIMEOUT_S = 15.0
#
#
MISSED_ACKS = 3
#
FRAMES_PER_SECOND = protocol.MAX_FRAMES_PER_SECOND // 2
#
#
RECEIVE_SLICE_S = 1.0
#
OUTBOX_SLICE_S = 0.01
#
SHOWN_MAX = 200
#
#
HURRY_S = 2.0
#
#
EARLY_BEAT_S = 1.0
#
#
#
READ_AHEAD_S = 5.0

#
_REFUSALS = {
    protocol.ErrorCode.REVOKED: (
        "the hub revoked this rig's token (the rig was deleted, or its token "
        "rotated); join again with a token the hub issues now"
    ),
    protocol.ErrorCode.MACHINE_MISMATCH: (
        "the hub has this rig bound to another machine (a rig's token binds to "
        "the first machine that says hello with it, and a machine whose cards "
        "changed is another machine); create a rig for this machine on the hub "
        "and join with its token"
    ),
    protocol.ErrorCode.UNSUPPORTED_VERSION: (
        "the hub speaks another version of the agent protocol; update mcgyvr"
    ),
    protocol.ErrorCode.SUPERSEDED: (
        "another agent with this rig's token took over the rig; this one stops "
        "so the two do not take it from each other"
    ),
    protocol.ErrorCode.EXPECTED_HELLO: (
        "the hub did not take this agent's hello; update mcgyvr"
    ),
}


class Channel(Protocol):
    ""

    def send_text(self, text: str) -> None: ...

    def receive(self, timeout: float) -> str | bytes | None: ...

    def wake(self) -> None:
        ""
        ...

    def close(self, code: int = 1000, reason: str = "") -> None: ...


@dataclass(frozen=True, kw_only=True)
class Backoff:
    ""

    first_s: float = 1.0
    factor: float = 2.0
    cap_s: float = 60.0
    steady_s: float = 60.0

    def delay(self, attempt: int, draw: float) -> float:
        ""
        ceiling = min(self.cap_s, self.first_s * self.factor ** min(attempt, 64))
        return ceiling / 2 + draw * ceiling / 2


@dataclass(frozen=True, kw_only=True)
class Ended:
    ""

    stopped: bool
    why: str


@dataclass(frozen=True, kw_only=True)
class Status:
    ""

    connected: bool
    rig_id: str | None
    heartbeat_s: int | None
    last_ack_at: float | None


def shown(text: str) -> str:
    ""
    kept = "".join(c if protocol.CARD_NAME.fullmatch(c) else " " for c in text)
    kept = " ".join(kept.split())
    return kept if len(kept) <= SHOWN_MAX else kept[: SHOWN_MAX - 1] + "…"


def _say(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


class _LostError(Exception):
    ""


class _RefusedError(Exception):
    ""


class _StoppedError(Exception):
    ""


class _Session:
    ""

    def __init__(
        self,
        acked: Callable[[_Session], None],
        errors: Callable[[protocol.Error], None] = lambda error: None,
    ) -> None:
        self._told = acked
        self._errors = errors
        self.acked: set[str] = set()
        #
        #
        self.rig_id: str | None = None
        self.interval: int | None = None
        self.last_error: protocol.Error | None = None

    def on_ack(self, ack: protocol.Ack) -> None:
        self.acked.add(ack.re)
        if ack.rig_id is not None:
            self.rig_id = ack.rig_id
        if ack.heartbeat_interval_s is not None:
            self.interval = ack.heartbeat_interval_s
        self._told(self)

    def on_error(self, error: protocol.Error) -> None:
        self.last_error = error
        self._errors(error)


def _judge(failure: Exception, last_error: protocol.Error | None) -> Exception:
    ""
    said = (
        f" ({shown(last_error.message)})" if last_error and last_error.message else ""
    )
    if isinstance(failure, websocket.HandshakeError):
        if failure.status in (401, 403):
            return _RefusedError(
                "the hub refused this rig's token; check the token the hub "
                "showed when the rig was created, or rotate it and join again"
            )
        if failure.status == 404:
            return _LostError(
                "the hub's address answered HTTP 404: no agent channel is there "
                "now (a proxy answers so while the hub behind it restarts); if "
                "this goes on, check the hub's address"
            )
        return _LostError(f"the hub could not be reached: {shown(str(failure))}")
    if isinstance(failure, websocket.ClosedError):
        code = failure.code
        if code == protocol.CloseCode.REVOKED:
            return _RefusedError(_REFUSALS[protocol.ErrorCode.REVOKED])
        if code == protocol.CloseCode.SUPERSEDED:
            return _RefusedError(_REFUSALS[protocol.ErrorCode.SUPERSEDED])
        if last_error is not None and last_error.code in _REFUSALS:
            return _RefusedError(_REFUSALS[protocol.ErrorCode(last_error.code)] + said)
        reason = f": {shown(failure.reason)}" if failure.reason else ""
        return _LostError(f"the channel closed with {code}{reason}{said}")
    return _LostError(shown(str(failure)))


def _aside(job: Callable[[], None]) -> None:
    threading.Thread(target=job, name="rig-reading", daemon=True).start()


class _Readings:
    ""

    def __init__(
        self,
        read: Callable[[], hardware.Report],
        aside: Callable[[Callable[[], None]], None],
    ) -> None:
        self._read = read
        self._aside = aside
        self._lock = threading.Lock()
        self.kept: tuple[int, hardware.Report | hardware.HardwareError] = (
            0,
            hardware.HardwareError("the machine was not read yet"),
        )
        self.begun = 0
        self.ended = 0
        self.running = False

    def hand(self, report: hardware.Report) -> None:
        ""
        with self._lock:
            self.kept = (self.begun, report)

    def begin(self, wake: Callable[[], None]) -> None:
        ""
        self.running = True
        self.begun += 1
        number = self.begun

        def job() -> None:
            outcome: hardware.Report | hardware.HardwareError
            try:
                try:
                    outcome = self._read()
                except hardware.HardwareError as exc:
                    outcome = exc
                with self._lock:
                    if number > self.kept[0]:
                        self.kept = (number, outcome)
            finally:
                with self._lock:
                    self.running = False
                    self.ended += 1
                wake()

        self._aside(job)


class Agent:
    ""

    def __init__(
        self,
        *,
        connect: Callable[[], Channel],
        read_hardware: Callable[[], hardware.Report],
        agent_version: str,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
        wait: Callable[[float], bool] | None = None,
        draw: Callable[[], float] = random.random,
        say: Callable[[str], None] = _say,
        backoff: Backoff | None = None,
        dispatcher: commands.Dispatcher | None = None,
        on_status: Callable[[Status], None] | None = None,
        outbox: Outbox | None = None,
        offer: Callable[[], protocol.Offer | None] | None = None,
        on_online: Callable[[], None] | None = None,
        on_offline: Callable[[], None] | None = None,
        on_exit: Callable[[], None] | None = None,
        hurry: Callable[[], bool] | None = None,
        on_hub_error: Callable[[protocol.Error], None] | None = None,
        on_beat: Callable[[], None] | None = None,
        aside: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        self._connect = connect
        self._read = read_hardware
        #
        self._readings = _Readings(read_hardware, aside or _aside)
        self._version = agent_version
        self._clock = clock
        self._wall = wall
        self._stopping = threading.Event()
        self._wait = wait or self._stopping.wait
        self._draw = draw
        self._say = say
        self._backoff = backoff or Backoff()
        self._dispatcher = dispatcher or commands.Dispatcher()
        self._on_status = on_status or (lambda status: None)
        self._sent: deque[float] = deque()
        self._outbox = outbox
        self._offer = offer
        self._on_online = on_online or (lambda: None)
        self._on_offline = on_offline or (lambda: None)
        self._on_exit = on_exit or (lambda: None)
        self._hurry = hurry or (lambda: False)
        self._on_hub_error = on_hub_error or (lambda error: None)
        self._on_beat = on_beat or (lambda: None)
        self._soon = threading.Event()

    def beat_soon(self) -> None:
        ""
        self._soon.set()

    def stop(self) -> None:
        ""
        self._stopping.set()

    def run(self) -> Ended:
        ""
        attempt = 0
        try:
            return self._sessions(attempt)
        finally:
            self._on_exit()

    def _sessions(self, attempt: int) -> Ended:
        try:
            while True:
                if self._stopping.is_set():
                    raise _StoppedError
                held_from: list[float] = []
                try:
                    self._session(held_from)
                except _LostError as lost:
                    held = bool(held_from) and (
                        self._clock() - held_from[0] >= self._backoff.steady_s
                    )
                    attempt = 0 if held else attempt
                    delay = self._backoff.delay(attempt, self._draw())
                    if self._hurry():
                        delay = min(delay, HURRY_S)
                    attempt += 1
                    self._status(connected=False)
                    self._say(f"lost the hub: {lost}; trying again in {delay:.1f} s")
                    if self._wait(delay):
                        raise _StoppedError from None
        except _RefusedError as refused:
            self._status(connected=False)
            self._say(f"refused: {refused}")
            return Ended(stopped=False, why=str(refused))
        except (_StoppedError, KeyboardInterrupt):
            self._status(connected=False)
            self._say("stopped")
            return Ended(stopped=True, why="asked to stop")

    #

    def _status(
        self,
        *,
        connected: bool,
        session: _Session | None = None,
        acked: float | None = None,
    ) -> None:
        self._on_status(
            Status(
                connected=connected,
                rig_id=session.rig_id if session else None,
                heartbeat_s=session.interval if session else None,
                last_ack_at=acked,
            )
        )

    def _room(self) -> int:
        ""
        now = self._clock()
        while self._sent and now - self._sent[0] >= 1.0:
            self._sent.popleft()
        return FRAMES_PER_SECOND - 1 - len(self._sent)

    def _send(self, channel: Channel, frame: str, *, answer: bool) -> bool:
        ""
        if answer and self._room() <= 0:
            return self._outbox is not None and self._outbox.put(frame, timeout=0)
        channel.send_text(frame)
        self._sent.append(self._clock())
        return True

    def _drain(self, channel: Channel) -> None:
        ""
        while self._outbox is not None and self._room() > 0:
            frame = self._outbox.take()
            if frame is None:
                return
            #
            #
            channel.send_text(frame if isinstance(frame, str) else frame())
            self._sent.append(self._clock())

    def _session(self, held_from: list[float]) -> None:
        try:
            report = self._read()
        except hardware.HardwareError as exc:
            raise _LostError(f"this machine could not be read: {exc}") from exc
        try:
            channel = self._connect()
        except (websocket.WebSocketError, OSError) as exc:
            raise _judge(exc, None) from exc
        session = _Session(
            lambda told: self._status(connected=True, session=told, acked=self._wall()),
            self._on_hub_error,
        )
        try:
            self._converse(channel, session, report, held_from)
        except (websocket.WebSocketError, OSError) as exc:
            raise _judge(exc, session.last_error) from exc
        except (_StoppedError, KeyboardInterrupt):
            channel.close(1000, "agent stopped")
            raise
        except _LostError:
            channel.close(1000, "agent gave up on the channel")
            raise
        finally:
            if self._outbox is not None:
                self._outbox.close()
            if held_from:
                self._on_offline()

    def _pump(
        self,
        channel: Channel,
        session: _Session,
        until: float,
        done: Callable[[], bool] = lambda: False,
    ) -> None:
        ""
        while not done():
            if self._stopping.is_set():
                raise _StoppedError
            self._drain(channel)
            left = until - self._clock()
            if left <= 0:
                return
            waiting = self._outbox is not None and self._outbox.pending()
            slice_s = OUTBOX_SLICE_S if waiting else RECEIVE_SLICE_S
            raw = channel.receive(timeout=min(left, slice_s))
            if raw is None:
                continue
            answer = self._dispatcher.dispatch(raw, session)
            if answer is not None:
                self._send(channel, answer, answer=True)

    def _news(self, ended: int, asks: bool) -> Callable[[], bool]:
        ""
        return lambda: self._readings.ended != ended or (asks and self._soon.is_set())

    def _converse(
        self,
        channel: Channel,
        session: _Session,
        report: hardware.Report,
        held_from: list[float],
    ) -> None:
        hello_id = protocol.new_id()
        offer = None
        if self._offer is not None:
            try:
                offer = self._offer()
            except (OSError, ValueError) as exc:
                self._say(f"note: this hello offers nothing: {shown(str(exc))}")
        self._send(
            channel,
            hardware.hello_frame(
                report, hello_id, agent_version=self._version, offer=offer
            ),
            answer=False,
        )
        deadline = self._clock() + HELLO_ACK_TIMEOUT_S
        while hello_id not in session.acked:
            if self._clock() >= deadline:
                raise _LostError(
                    f"the hub did not ack the hello in {HELLO_ACK_TIMEOUT_S:g} s"
                )
            self._pump(
                channel,
                session,
                deadline,
                done=lambda: hello_id in session.acked,
            )
        held_from.append(self._clock())
        if self._outbox is not None:
            self._outbox.open(wake=channel.wake)
        self._on_online()
        interval = session.interval or DEFAULT_HEARTBEAT_S
        rig = shown(session.rig_id) if session.rig_id else "a rig"
        self._say(
            f"online as {rig}: {len(report.cards)} card(s), "
            f"{report.ram_total_mb} MiB RAM; a heartbeat every {interval} s"
        )
        for note in report.notes:
            self._say(f"note: {note}")
        readings = self._readings
        readings.hand(report)
        ahead = min(READ_AHEAD_S, interval)
        unacked: list[str] = []
        next_beat = self._clock() + interval
        last_beat = self._clock()
        read_for: float | None = None  #
        early: int | None = None  #
        while True:
            ended = readings.ended  #
            if early is None and self._soon.is_set():
                self._soon.clear()
                early = readings.begun + 1  #
            now = self._clock()
            if read_for != next_beat and now >= next_beat - ahead:
                read_for = next_beat  #
                if not readings.running:
                    readings.begin(channel.wake)
            if early is not None and readings.begun < early and not readings.running:
                readings.begin(channel.wake)
            number, outcome = readings.kept
            ready = early is not None and number >= early
            early_at = last_beat + EARLY_BEAT_S
            if now < next_beat and not (ready and now >= early_at):
                until = next_beat
                if read_for != next_beat:
                    until = min(until, next_beat - ahead)
                if ready:
                    until = min(until, early_at)
                self._pump(
                    channel, session, until, done=self._news(ended, early is None)
                )
                continue
            if any(beat in session.acked for beat in unacked):
                unacked.clear()
            session.acked.clear()  #
            if len(unacked) >= MISSED_ACKS:
                raise _LostError(
                    f"the hub acked none of the last {MISSED_ACKS} heartbeats"
                )
            beat_id = protocol.new_id()
            if isinstance(outcome, hardware.HardwareError):
                self._say(f"note: this heartbeat carries no reading: {outcome}")
                frame = protocol.heartbeat(beat_id, ram_free_mb=None, cards=())
            else:
                frame = hardware.heartbeat_frame(outcome, beat_id)
            self._send(channel, frame, answer=False)
            unacked.append(beat_id)
            last_beat = self._clock()
            self._on_beat()
            if ready:
                early = None
            if now >= next_beat:
                next_beat += interval
