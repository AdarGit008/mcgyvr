"""The rig agent: one session at a time with the hub, and the reconnects between.

A session reads the machine (:mod:`mcgyvr.rig.hardware`) before it connects,
so the hub never sees a channel open without a hello. It opens the channel,
says ``hello`` first and waits for the hub's ``ack``, which names the rig and
sets the heartbeat interval. Then it sends a heartbeat each interval, each
with a fresh reading, and hands every frame the hub sends to the dispatcher
(:mod:`mcgyvr.rig.commands`), sending back what it answers.

A session ends one of three ways, and each is judged once, by
:func:`_judge`:

* **asked to stop** — the channel is closed with 1000 and the agent ends;
* **refused** — the hub refused the token at the upgrade, revoked it, bound
  the rig to another machine, speaks another protocol version, or handed the
  rig to a newer agent. Asking again would be refused again (or would take
  the rig back from that newer agent, and so on, forever), so the agent ends
  and says what the user can do;
* **lost** — anything else: the channel dropped, the hub timed the agent out
  or throttled it, the hub could not be reached, the machine could not be
  read, a hello or :data:`MISSED_ACKS` heartbeats in a row went unacked. The
  agent waits (:class:`Backoff`) and starts a new session — no longer than
  :data:`HURRY_S` while the rig's sessions wait out the grace the hub keeps
  them for (``hurry``), so it is back in time for its hello to resume them.

The hub is untrusted. Whatever it sends, the agent answers at most
:data:`FRAMES_PER_SECOND` frames a second, under the hub's own cap, dropping
answers rather than heartbeats; and what it says (an error's text, a close's
reason, the rig id) is shown printable and short (:func:`shown`).

A rig that lends (:mod:`mcgyvr.rig.session`) says so in its hello (the
``offer``), and its sessions and relays speak on their own through the
outbox (:mod:`mcgyvr.rig.outbox`), which the agent empties between reads at
the same rate, delaying rather than dropping. The agent tells them when the
channel is up (``on_online``), when it is lost (``on_offline``: the outbox
is closed, and sessions end unless the hub returns within their grace), and
when the agent ends (``on_exit``: every session is torn down before
:meth:`Agent.run` returns). After each heartbeat it is sent the agent tells
``on_beat``, its one periodic tick: whatever hangs off it must return at once
and do its work elsewhere (the relief rungs' refresher,
:class:`mcgyvr.rig.rungs.Refresher`). An error the hub sends is told to them too
(``on_hub_error``), and a session that ended and freed its memory asks for a
heartbeat at once (:meth:`Agent.beat_soon`), so the hub's reading of the rig
is fresh.
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

from mcgyvr.rig import commands, hardware, protocol, websocket
from mcgyvr.rig.outbox import Outbox

#: The heartbeat interval when the hub's hello ack names none, in seconds:
#: the hub's own default.
DEFAULT_HEARTBEAT_S = 15
#: How long the agent waits for the hub to ack its hello, in seconds.
HELLO_ACK_TIMEOUT_S = 15.0
#: Heartbeats in a row the hub may leave unacked before the agent gives up on
#: the channel.
MISSED_ACKS = 3
#: The most frames the agent sends in any second: half the hub's cap.
FRAMES_PER_SECOND = protocol.MAX_FRAMES_PER_SECOND // 2
#: The longest single wait on the channel, in seconds, so a stop is heard.
RECEIVE_SLICE_S = 1.0
#: The longest wait on the channel while frames wait in the outbox, in seconds.
OUTBOX_SLICE_S = 0.01
#: The longest text of the hub's the agent shows, in characters.
SHOWN_MAX = 200
#: The longest wait before a new session while the rig's sessions wait out
#: the hub's grace, in seconds.
HURRY_S = 2.0
#: The soonest a heartbeat asked for early goes after the one before it (or
#: the hello), in seconds.
EARLY_BEAT_S = 1.0

#: Error codes after which asking again is refused again.
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
    """What a session needs of a channel: :class:`mcgyvr.rig.websocket.WebSocket`."""

    def send_text(self, text: str) -> None: ...

    def receive(self, timeout: float) -> str | bytes | None: ...

    def close(self, code: int = 1000, reason: str = "") -> None: ...


@dataclass(frozen=True, kw_only=True)
class Backoff:
    """The wait before a new session: ``first_s``, growing by ``factor`` with
    each session that ends lost, up to ``cap_s``, with up to half of it drawn
    at random so many agents do not return at once. A session that held for
    ``steady_s`` after its hello was acked starts the growth over."""

    first_s: float = 1.0
    factor: float = 2.0
    cap_s: float = 60.0
    steady_s: float = 60.0

    def delay(self, attempt: int, draw: float) -> float:
        """The wait before attempt ``attempt`` (from 0); ``draw`` in [0, 1]."""
        ceiling = min(self.cap_s, self.first_s * self.factor ** min(attempt, 64))
        return ceiling / 2 + draw * ceiling / 2


@dataclass(frozen=True, kw_only=True)
class Ended:
    """How the agent ended: ``stopped`` when asked to, else refused, and why."""

    stopped: bool
    why: str


@dataclass(frozen=True, kw_only=True)
class Status:
    """What the agent knows of its rig now, for ``mcgyvr rig status``."""

    connected: bool
    rig_id: str | None
    heartbeat_s: int | None
    last_ack_at: float | None


def shown(text: str) -> str:
    """The hub's ``text`` as it may be shown: printable, and short."""
    kept = "".join(c if protocol.CARD_NAME.fullmatch(c) else " " for c in text)
    kept = " ".join(kept.split())
    return kept if len(kept) <= SHOWN_MAX else kept[: SHOWN_MAX - 1] + "…"


def _say(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


class _LostError(Exception):
    """The session ended and a new one may be tried."""


class _RefusedError(Exception):
    """The hub refused, and would refuse again."""


class _StoppedError(Exception):
    """The agent was asked to stop."""


class _Session:
    """One channel's state, as the dispatcher reports to it; ``acked`` is told
    of each ack as it arrives, ``errors`` of each error."""

    def __init__(
        self,
        acked: Callable[[_Session], None],
        errors: Callable[[protocol.Error], None] = lambda error: None,
    ) -> None:
        self._told = acked
        self._errors = errors
        self.acked: set[str] = set()
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
    """A session's end as :class:`_RefusedError` or :class:`_LostError`."""
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
            return _RefusedError(
                "the hub has no agent channel at this address; check the hub's address"
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


class Agent:
    """The agent's loop. :meth:`run` until stopped or refused."""

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
    ) -> None:
        self._connect = connect
        self._read = read_hardware
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
        """Send a heartbeat now, or :data:`EARLY_BEAT_S` after the last: the
        rig's memory changed (a session ended)."""
        self._soon.set()

    def stop(self) -> None:
        """Ask the agent to stop; it closes its channel and :meth:`run` returns."""
        self._stopping.set()

    def run(self) -> Ended:
        """Sessions, with backoff between them, until stopped or refused."""
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

    # -- one session --

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
        """How many frames may go now, keeping one for a heartbeat."""
        now = self._clock()
        while self._sent and now - self._sent[0] >= 1.0:
            self._sent.popleft()
        return FRAMES_PER_SECOND - 1 - len(self._sent)

    def _send(self, channel: Channel, frame: str, *, answer: bool) -> bool:
        """Send ``frame``; an answer that would break the rate waits in the
        outbox, or is dropped when there is none."""
        if answer and self._room() <= 0:
            return self._outbox is not None and self._outbox.put(frame, timeout=0)
        channel.send_text(frame)
        self._sent.append(self._clock())
        return True

    def _drain(self, channel: Channel) -> None:
        """Send what waits in the outbox, as the rate allows."""
        while self._outbox is not None and self._room() > 0:
            frame = self._outbox.take()
            if frame is None:
                return
            channel.send_text(frame)
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
        """Handle what the hub sends until ``until`` on the clock, or ``done``."""
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

    def _early_after(self, at: float) -> Callable[[], bool]:
        """Whether a heartbeat asked for early may go now: asked, and at or
        after ``at`` on the clock."""
        return lambda: self._soon.is_set() and self._clock() >= at

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
            self._outbox.open()
        self._on_online()
        interval = session.interval or DEFAULT_HEARTBEAT_S
        rig = shown(session.rig_id) if session.rig_id else "a rig"
        self._say(
            f"online as {rig}: {len(report.cards)} card(s), "
            f"{report.ram_total_mb} MiB RAM; a heartbeat every {interval} s"
        )
        for note in report.notes:
            self._say(f"note: {note}")
        unacked: list[str] = []
        next_beat = self._clock() + interval
        last_beat = self._clock()
        while True:
            self._pump(
                channel,
                session,
                next_beat,
                done=self._early_after(last_beat + EARLY_BEAT_S),
            )
            early = self._soon.is_set() and self._clock() < next_beat
            self._soon.clear()
            if any(beat in session.acked for beat in unacked):
                unacked.clear()
            session.acked.clear()  # read; an id is acked once, so none is kept
            if len(unacked) >= MISSED_ACKS:
                raise _LostError(
                    f"the hub acked none of the last {MISSED_ACKS} heartbeats"
                )
            beat_id = protocol.new_id()
            try:
                frame = hardware.heartbeat_frame(self._read(), beat_id)
            except hardware.HardwareError as exc:
                self._say(f"note: this heartbeat carries no reading: {exc}")
                frame = protocol.heartbeat(beat_id, ram_free_mb=None, cards=())
            self._send(channel, frame, answer=False)
            unacked.append(beat_id)
            last_beat = self._clock()
            self._on_beat()
            if not early:
                next_beat += interval
