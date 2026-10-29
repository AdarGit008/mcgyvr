"""The rig's side of the agent protocol: one rig kept joined to its hub.

``Agent.run`` holds a channel open for as long as the hub allows it. Each
connection reads this machine, says hello with that reading and with the offer
of what the rig lends, waits for the hello's ack, then sends a heartbeat every
interval carrying a fresh reading and takes the hub's frames through a
``Dispatcher``. Readings are taken on a side thread ahead of the beat that
carries them and answers that find the send budget spent wait in an ``Outbox``,
so neither a slow machine nor a slow hub holds the other up. A channel that is
lost is retried with jittered backoff; a refusal (a token that is wrong,
revoked, superseded, or bound to another machine) is final, and ``run`` returns
why it ended for the caller to show.

Nothing here writes to the terminal except through ``say``, which goes to
stderr, and nothing here knows the hub's address or this machine's cards: both
arrive as callables from the caller.
"""

from __future__ import annotations

import random
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from mcgyvr import hubwire
from mcgyvr.rig import commands, hardware, protocol, websocket
from mcgyvr.rig.outbox import Outbox

#: How often a heartbeat goes out when the hub's ack named no interval of its
#: own; the hub sets an interval per rig, and this is only the fallback.
DEFAULT_HEARTBEAT_S = 15
#: Seconds the hello may wait for its ack before the channel is given up as dead.
HELLO_ACK_TIMEOUT_S = 15.0
#: Heartbeats that may go unanswered before the agent gives up on the channel;
#: one ack clears them all, since the hub acks as it reads rather than one by one.
MISSED_ACKS = 3
#: Frames this agent may send per second, half of the protocol's ceiling.
FRAMES_PER_SECOND = protocol.MAX_FRAMES_PER_SECOND // 2
#: Seconds one receive may wait while the outbox is empty, so the loop still
#: wakes often enough to notice a stop request or a heartbeat falling due.
RECEIVE_SLICE_S = 1.0
#: A shorter receive slice while frames wait in the outbox, so they leave early.
OUTBOX_SLICE_S = 0.01
#: Longest text ``shown`` returns; anything longer is cut with an ellipsis.
SHOWN_MAX = 200
#: Ceiling on the reconnect delay while ``hurry`` says a person is waiting, so a
#: hub that is coming back is rejoined in seconds rather than by backoff.
HURRY_S = 2.0
#: Seconds a heartbeat asked for by ``beat_soon`` waits after the one before it,
#: so an early beat does not put two beats back to back on the hub.
EARLY_BEAT_S = 1.0
#: Seconds before a heartbeat falls due that its reading is started, never more
#: than one interval: the read runs on a side thread, so the beat carries what
#: was newest when it went out and a slow machine delays no beat.
READ_AHEAD_S = 5.0

#: What a person is told for each error the hub can refuse a rig for good with.
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
    """The agent's link to the hub: frames out, whatever arrives in, a close."""

    def send_text(self, text: str) -> None: ...

    def receive(self, timeout: float) -> str | bytes | None: ...

    def wake(self) -> None:
        """Make a waiting receive return soon, so the loop sees queued frames."""
        ...

    def close(self, code: int = 1000, reason: str = "") -> None: ...


@dataclass(frozen=True, kw_only=True)
class Backoff:
    """Reconnect delays that grow from ``first_s`` by ``factor`` up to ``cap_s``.

    ``delay`` jitters each one so many rigs do not retry in step, and a session
    that lasted ``steady_s`` counts as a fresh start: the delay after it begins
    short again instead of resuming where the failed attempts had climbed to.
    """

    first_s: float = 1.0
    factor: float = 2.0
    cap_s: float = 60.0
    steady_s: float = 60.0

    def delay(self, attempt: int, draw: float) -> float:
        """Seconds to wait before retry ``attempt``, ``draw`` (0 to 1) picking
        a point in the upper half of the ceiling."""
        ceiling = min(self.cap_s, self.first_s * self.factor ** min(attempt, 64))
        return ceiling / 2 + draw * ceiling / 2


@dataclass(frozen=True, kw_only=True)
class Ended:
    """How a run ended: asked to stop, or refused, and the reason to show."""

    stopped: bool
    why: str


@dataclass(frozen=True, kw_only=True)
class Status:
    """What the agent last knew of its connection, for whatever shows the rig."""

    connected: bool
    rig_id: str | None
    heartbeat_s: int | None
    last_ack_at: float | None


def shown(text: str) -> str:
    """Text fit to print: only characters a card name may hold, whitespace
    squeezed, and anything past ``SHOWN_MAX`` cut with an ellipsis."""
    kept = "".join(c if protocol.CARD_NAME.fullmatch(c) else " " for c in text)
    kept = " ".join(kept.split())
    return kept if len(kept) <= SHOWN_MAX else kept[: SHOWN_MAX - 1] + "…"


def _say(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


class _LostError(Exception):
    """The channel is gone, but another attempt may get past what took it."""


class _LendsChangedError(_LostError):
    """What the rig lends changed since its hello: a new hello says it, at once."""


def _lends(report: hardware.Report) -> frozenset[tuple[str, int, int, int | None]]:
    """What a report lends, as a hub keeps it from the hello: each resource's
    kind, index, size and cores (its free memory is what heartbeats re-read)."""
    return frozenset((r.kind, r.index, r.total_mb, r.cores) for r in report.lent)


class _RefusedError(Exception):
    """The hub refused this rig for good; the same token will not do again."""


class _StoppedError(Exception):
    """The agent was asked to stop, or the run was interrupted."""


class _Session:
    """What one connection learned from the hub, filled in as its frames arrive.

    ``acked`` collects the ids of frames the hub has acked, which is what the
    hello's timeout, the heartbeat count, and the send budget are read from.
    """

    def __init__(
        self,
        acked: Callable[[_Session], None],
        errors: Callable[[protocol.Error], None] = lambda error: None,
    ) -> None:
        self._told = acked
        self._errors = errors
        self.acked: set[str] = set()
        #: The rig id and the heartbeat interval arrive with an ack, and the last
        #: error is kept so a close can be explained by what the hub said first.
        self.rig_id: str | None = None
        self.interval: int | None = None
        self.last_error: protocol.Error | None = None
        #: What the member chose on the hub for this rig to lend, when said.
        self.lending: hubwire.Lending | None = None
        self.lending_unread: str | None = None

    def on_ack(self, ack: protocol.Ack) -> None:
        self.acked.add(ack.re)
        if ack.lending is not None:
            self.lending = ack.lending
        if ack.lending_unread is not None:
            self.lending_unread = ack.lending_unread
        if ack.rig_id is not None:
            self.rig_id = ack.rig_id
        if ack.heartbeat_interval_s is not None:
            self.interval = ack.heartbeat_interval_s
        self._told(self)

    def on_error(self, error: protocol.Error) -> None:
        self.last_error = error
        self._errors(error)


def _judge(failure: Exception, last_error: protocol.Error | None) -> Exception:
    """Read a transport failure as the error that decides what happens next: a
    refusal for a token the hub will not take or another agent's takeover, a
    loss for anything another attempt may get past."""
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
    """This machine read on a side thread, so a slow read holds up no beat.

    Each read is numbered: ``kept`` is the newest reading with the number it was
    given, so a read that finishes late cannot replace a newer one, and ``ended``
    counts finished reads so a waiting session can tell one has landed.
    """

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
        """Keep a reading the caller already made, numbered as reads are now, so
        a read still under way cannot replace it with older news."""
        with self._lock:
            self.kept = (self.begun, report)

    def begin(self, wake: Callable[[], None]) -> None:
        """Start a numbered read on a side thread and wake the session once it
        has landed, whatever the machine answered."""
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
    """Keeps one rig joined to its hub: hello, heartbeats with readings, the
    hub's commands, and reconnection until the hub refuses the rig or a caller
    stops it."""

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
        on_lending: Callable[[hubwire.Lending | None], None] | None = None,
    ) -> None:
        self._connect = connect
        self._read = read_hardware
        # Readings run on a thread of the agent's own unless the caller says how
        # to start one, which is what lets a test read in the calling thread.
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
        self._on_lending = on_lending or (lambda lending: None)
        self._soon = threading.Event()

    def beat_soon(self) -> None:
        """Ask for a heartbeat as soon as one may go out, so news the hub is
        waiting on need not wait for the next beat that is due."""
        self._soon.set()

    def stop(self) -> None:
        """Ask the agent to stop: a reconnect wait ends at once, and ``run``
        returns as soon as the channel is closed."""
        self._stopping.set()

    def run(self) -> Ended:
        """Stay joined and answering until stopped or refused, then say which."""
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
                except _LendsChangedError as changed:
                    self._status(connected=False)
                    self._say(f"{changed}; saying hello again")
                    continue
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

    # The parts of a run: what to report, what may be sent, and the one channel
    # at a time that the hello, the heartbeats, and the hub's frames go over.

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
        """Frames that may still be sent this second, one slot held back for the
        send that is asking."""
        now = self._clock()
        while self._sent and now - self._sent[0] >= 1.0:
            self._sent.popleft()
        return FRAMES_PER_SECOND - 1 - len(self._sent)

    def _send(self, channel: Channel, frame: str, *, answer: bool) -> bool:
        """Send a frame now; an answer that finds the send budget spent goes to
        the outbox instead. False means it was neither sent nor queued."""
        if answer and self._room() <= 0:
            return self._outbox is not None and self._outbox.put(frame, timeout=0)
        channel.send_text(frame)
        self._sent.append(self._clock())
        return True

    def _drain(self, channel: Channel) -> None:
        """Hand queued frames to the channel while the send budget has room."""
        while self._outbox is not None and self._room() > 0:
            frame = self._outbox.take()
            if frame is None:
                return
            # A queued frame is text, or something that makes the text when the
            # frame is taken, so a frame that reads this machine is made late.
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
        """Serve the channel until ``until`` or until ``done`` says to stop:
        drain the outbox, take whatever the hub sends, answer it."""
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
        """A ``done`` test for ``_pump``: true once a side read has landed since
        ``ended``, or when a heartbeat is asked for and ``asks`` says the loop is
        still waiting on one."""
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
        if session.lending_unread is not None:
            self._say(
                "note: the hub's lending choice is not taken "
                f"({shown(session.lending_unread)}); lending as this rig's "
                "settings say"
            )
        # The member's choice on the hub, or None when the hub asks nothing
        # (or sent a lending not taken): the next reading lends it, and a
        # heartbeat that finds the lend changed says hello again.
        self._on_lending(session.lending)
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
        lends = _lends(report)
        readings = self._readings
        readings.hand(report)
        ahead = min(READ_AHEAD_S, interval)
        unacked: list[str] = []
        next_beat = self._clock() + interval
        last_beat = self._clock()
        read_for: float | None = None  # which beat the read under way is for
        early: int | None = None  # the read an early beat waits for, if asked
        while True:
            ended = readings.ended  # so _pump returns once a read has landed
            if early is None and self._soon.is_set():
                self._soon.clear()
                early = readings.begun + 1  # the read this early beat will carry
            now = self._clock()
            if read_for != next_beat and now >= next_beat - ahead:
                read_for = next_beat  # one read per beat: which beat it is for
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
            session.acked.clear()  # the acks this beat needed are all counted now
            if len(unacked) >= MISSED_ACKS:
                raise _LostError(
                    f"the hub acked none of the last {MISSED_ACKS} heartbeats"
                )
            if (
                not isinstance(outcome, hardware.HardwareError)
                and _lends(outcome) != lends
            ):
                # A hub keeps what the hello lent and reads only those again:
                # a change (lent, or taken back) needs a new hello to be heard.
                raise _LendsChangedError("what this rig lends changed")
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
