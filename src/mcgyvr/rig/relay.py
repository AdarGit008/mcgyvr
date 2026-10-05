"""Relaying one request from the hub to the head this rig serves, and its answer back.

The hub relays OpenAI-compatible requests to a session's head; on the head's
rig the agent is the only way in, since the head's API is published on this
machine's loopback alone (:mod:`mcgyvr.sandbox.pooled`). A relay is:

* ``relay_request``, then the body in ``relay_data`` frames numbered from 0,
  exactly as many bytes as announced — a frame out of order, or bytes past
  the announced count, end the relay;
* one ``POST`` of that body to the one path the relayed endpoint maps to
  (:data:`mcgyvr.rig.sessionwire.RELAY_PATHS`) on ``127.0.0.1``, at the port
  the session's head was published on. The hub names an endpoint, never a
  path, a host or a port: this is no general proxy;
* the answer as ``relay_response`` (status, content type), then ``relay_data``
  frames of at most :data:`~mcgyvr.rig.sessionwire.RELAY_MAX_CHUNK_BYTES`
  each, never more of them uncredited than the hub's window: out of credit,
  the relay stops reading the head, and the head's own socket holds it. A
  frame is filled when the agent takes it to send, not when it is queued
  (:meth:`Relays._data`): it carries all the head wrote up to then, and one
  frame of a relay waits at a time. The agent's frame rate is for all the
  rig's relays together and a head writes each token as an event of its own,
  so a frame per read would cap the rig's tokens at that rate; filled late,
  a frame that waited its turn carries the events written meanwhile, and the
  first is not held back for more. The bytes go unchanged and in order, and
  a relay whose full frame waits stops reading the head;
* exactly one ``relay_end`` — ``complete``; ``cancelled`` on the hub's
  ``relay_cancel`` or when the session ends; ``timeout`` past the hub's time;
  ``too_large`` past its size; or ``error`` with the hub's code.

A head serves as many requests at once as it has slots (``head_start``'s
``slots``), so a session takes at most that many relays at once, and the
next is answered ``busy`` without reaching the head. :data:`MAX_ACTIVE`
bounds each head's relays besides, never below what a head may take: a rig
may serve several heads at once (a session per card), and a head with a
slot free is never refused because another head is full.

A ride (``unit_relay_request``) is the same relay aimed elsewhere: at a unit
this host runs for themselves and shares with riders (hitchhike,
:mod:`mcgyvr.rig.hitchhike`), named by the id its advert gave it. The frames,
the credit, the deadline and the one ``relay_end`` are the head relay's, by
this same code; only the :class:`Target` differs. It is the unit's own
address, from the host's setup and never from the hub, joined to the
endpoint's one path as a run joins it, so this stays no general proxy. A unit
no advert named ends ``unknown_unit``; a unit that has its riders, or whose
host would be left short, ends ``busy`` (:meth:`Units.ride`, which also holds
one of the unit's slots for as long as the ride runs). The body goes as the
hub gave it, with the unit's model already in it, and the answer comes back as
the unit gives it. The rides together are bounded by :data:`MAX_ACTIVE` as a
head's relays are, and share the relays' request ids.

A cancel or a deadline hangs up on the head, which stops generating: so
does a requester who leaves mid-answer (the hub cancels the relay, or its
channel takes no more frames), a normal end that is one ``relay_end`` and
nothing printed. A relay the hub cancels says in that ``relay_end`` what its
head made by then (``tokens_in``, ``tokens_out``), which the hub charges the
requester who left: the head's own status page (:data:`SLOTS_PATH`) is read
just before the hang-up, on a thread of its own, never the one that hears
the hub. The page does not say which slot serves which request, so the
counts go only when the slot at work cannot be another's
(:meth:`Relays._made`); in any doubt, and for a ride, the relay ends with no
counts, as it always did, and the hub keeps to what it did before. Hanging up
shuts the head's socket down under the relay's read and no more; the relay's
own thread, woken by it, closes the connection.
``http.client`` closed from another thread while a read of it ends fails in
whichever loses (an ``AttributeError`` on the file it no longer has), so the
connection is closed by the one thread that reads it. What a
relay carries is the users' and is never printed or put in a message: a
failure says only its class.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import socket
import threading
import time
import urllib.parse
from collections import deque
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from typing import Protocol

from mcgyvr.rig import commands, protocol, sessionwire
from mcgyvr.rig.protocol import ErrorCode, ProtocolError
from mcgyvr.rig.sessionwire import SessionCode

#: How many relays may run at once to one head, and how many rides to the
#: shared units together: a safety net under each head's own bound (its
#: slots) and each unit's (its riders), never below the most slots one head
#: may have. It bounds each head, not the rig: a rig in several sessions at
#: once serves each head its own slots.
MAX_ACTIVE = sessionwire.MAX_SLOTS
#: How many request ids are remembered, so one is never used twice.
REMEMBERED_IDS = 4096
#: The longest a frame of the answer waits for the outbox, in seconds.
SEND_WAIT_S = 30.0
#: llama.cpp's status page, on the head's own API: each slot, whether it is
#: at work, and its counts.
SLOTS_PATH = "/slots"
#: The longest a cancelled relay's hang-up waits for that page, in seconds:
#: under the moment the hub waits for the ``relay_end``.
REPORT_WAIT_S = 1.0
#: The most of that page that is read, in bytes.
MAX_PAGE_BYTES = 1 << 20


class Heads(Protocol):
    """Where a session's head is: :class:`mcgyvr.rig.session.Sessions`."""

    def head_port(self, session_id: str) -> int | None: ...

    def head_slots(self, session_id: str) -> int: ...

    def state_of(self, session_id: str) -> tuple[str, str | None]: ...


class RideRefusedError(Exception):
    """A ride its unit will not take now; ``code`` is what its ``relay_end``
    says."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class Ride(Protocol):
    """An advertised unit as a ride reaches it: :class:`mcgyvr.rig.hitchhike.Shared`."""

    @property
    def rider_cap(self) -> int: ...

    def url(self, endpoint: str) -> str: ...


class Units(Protocol):
    """The units this host shares: :class:`mcgyvr.rig.hitchhike.Units`."""

    def advertised(self, unit_id: str) -> Ride | None: ...

    def ride(self, unit_id: str) -> AbstractContextManager[None]: ...


@dataclass(frozen=True)
class Target:
    """Where a relay's one ``POST`` goes: a host, a port and a path, over TLS
    or not. A head's is its loopback port; a ride's its unit's address."""

    host: str
    port: int
    path: str
    tls: bool = False

    @classmethod
    def loopback(cls, port: int, endpoint: str) -> Target:
        """The head's API, published on this machine's loopback at ``port``."""
        return cls("127.0.0.1", port, sessionwire.RELAY_PATHS[endpoint])

    @classmethod
    def of_url(cls, url: str) -> Target:
        """The target ``url`` names; ``ValueError`` when it is no http(s) URL."""
        parts = urllib.parse.urlsplit(url)
        scheme = parts.scheme.lower()
        if scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("a unit's address is an http(s) URL")
        tls = scheme == "https"
        port = parts.port or (443 if tls else 80)
        return cls(parts.hostname, port, parts.path or "/", tls)

    def connect(self, timeout: float) -> http.client.HTTPConnection:
        if self.tls:
            return http.client.HTTPSConnection(self.host, self.port, timeout=timeout)
        return http.client.HTTPConnection(self.host, self.port, timeout=timeout)


type _Asked = sessionwire.RelayRequest | sessionwire.UnitRelayRequest


def _admitted() -> AbstractContextManager[None]:
    return nullcontext()


@dataclass(eq=False)
class _Relay:
    asked: _Asked
    target: Target
    admit: Callable[[], AbstractContextManager[None]] = _admitted
    body: bytearray = field(default_factory=bytearray)
    next_seq: int = 0
    credit: int = 0
    outcome: str | None = None  # why it ends early, once decided
    code: str | None = None
    ended: bool = False
    changed: threading.Condition = field(default_factory=threading.Condition)
    connection: http.client.HTTPConnection | None = None
    deadline: float = 0.0
    working: bool = False  # the head has the request and has not answered it
    made: tuple[int, int] | None = None  # the head's counts, read at a cancel
    pending: bytearray = field(default_factory=bytearray)  # read, in no frame yet
    queued: bool = False  # a frame of the answer waits to be sent
    seq: int = 0  # the next frame of the answer

    @property
    def complete(self) -> bool:
        return len(self.body) == self.asked.body_bytes


class Relays:
    """The relays running on this rig, by request id."""

    def __init__(
        self,
        *,
        heads: Heads,
        send: Callable[..., bool],
        max_active: int = MAX_ACTIVE,
        clock: Callable[[], float] = time.monotonic,
        units: Units | None = None,
    ) -> None:
        self._heads = heads
        self._units = units
        self._send = send
        self._max_active = max_active
        self._clock = clock
        self._lock = threading.Lock()
        self._active: dict[str, _Relay] = {}
        self._begun = 0  # relays ever begun: one more, and a head is not as it was
        self._used: deque[str] = deque(maxlen=REMEMBERED_IDS)
        self._used_set: set[str] = set()

    # -- the handlers --------------------------------------------------------

    def request(self, envelope: protocol.Envelope) -> str | None:
        """``relay_request``: every one is answered with one ``relay_end``."""
        try:
            asked = sessionwire.read_relay_request(envelope)
        except ProtocolError:
            refused = self._unread(envelope)
            if refused is None:
                raise
            return refused
        with self._lock:
            if asked.request_id in self._used_set:
                return sessionwire.relay_end(
                    asked.request_id, outcome="error", error_code=SessionCode.DUPLICATE
                )
            self._remember(asked.request_id)
            port = self._heads.head_port(asked.session_id)
            if port is None:
                return sessionwire.relay_end(
                    asked.request_id,
                    outcome="error",
                    error_code=self._why_not(asked.session_id),
                )
            taken = sum(
                1
                for running in self._active.values()
                if isinstance(running.asked, sessionwire.RelayRequest)
                and running.asked.session_id == asked.session_id
            )
            if taken >= min(self._heads.head_slots(asked.session_id), self._max_active):
                return sessionwire.relay_end(
                    asked.request_id, outcome="error", error_code=SessionCode.BUSY
                )
            relay = _Relay(
                asked=asked,
                target=Target.loopback(port, asked.endpoint),
                credit=asked.window,
                deadline=self._clock() + asked.timeout_s,
            )
            self._active[asked.request_id] = relay
            self._begun += 1
        threading.Thread(
            target=self._run, args=(relay,), name="mcgyvr-relay", daemon=True
        ).start()
        return None

    def unit_request(self, envelope: protocol.Envelope) -> str | None:
        """``unit_relay_request``: a ride, answered with one ``relay_end`` as a
        relay is. Refused here at once: an id no advert named, a unit with its
        riders already, a rig at its bound. The host's own load is read on the
        ride's thread (:meth:`Units.ride`), since reading a server takes time."""
        try:
            asked = sessionwire.read_unit_relay_request(envelope)
        except ProtocolError:
            refused = self._unread(envelope)
            if refused is None:
                raise
            return refused
        units = self._units
        with self._lock:
            if asked.request_id in self._used_set:
                return sessionwire.relay_end(
                    asked.request_id, outcome="error", error_code=SessionCode.DUPLICATE
                )
            self._remember(asked.request_id)
            unit = None if units is None else units.advertised(asked.unit_id)
            if units is None or unit is None:
                return sessionwire.relay_end(
                    asked.request_id,
                    outcome="error",
                    error_code=SessionCode.UNKNOWN_UNIT,
                )
            rides = [
                running.asked
                for running in self._active.values()
                if isinstance(running.asked, sessionwire.UnitRelayRequest)
            ]
            riding = sum(1 for ride in rides if ride.unit_id == asked.unit_id)
            if riding >= unit.rider_cap or len(rides) >= self._max_active:
                return sessionwire.relay_end(
                    asked.request_id, outcome="error", error_code=SessionCode.BUSY
                )
            try:
                target = Target.of_url(unit.url(asked.endpoint))
            except ValueError:
                return sessionwire.relay_end(
                    asked.request_id,
                    outcome="error",
                    error_code=SessionCode.UPSTREAM_FAILED,
                )
            unit_id = asked.unit_id
            relay = _Relay(
                asked=asked,
                target=target,
                admit=lambda: units.ride(unit_id),
                credit=asked.window,
                deadline=self._clock() + asked.timeout_s,
            )
            self._active[asked.request_id] = relay
            self._begun += 1
        threading.Thread(
            target=self._run, args=(relay,), name="mcgyvr-relay", daemon=True
        ).start()
        return None

    def data(self, envelope: protocol.Envelope) -> str | None:
        """``relay_data`` from the hub: the next piece of a request's body."""
        piece = sessionwire.read_relay_data(envelope)
        with self._lock:
            relay = self._active.get(piece.request_id)
        if relay is None:
            return sessionwire.refusal(
                envelope.id,
                ErrorCode.BAD_MESSAGE,
                "request_id: no relay of this rig is taking a body",
            )
        with relay.changed:
            if relay.outcome is not None or relay.complete:
                return None
            if piece.seq != relay.next_seq:
                self._decide(relay, "error", ErrorCode.BAD_MESSAGE)
            elif len(relay.body) + len(piece.data) > relay.asked.body_bytes:
                self._decide(relay, "too_large", SessionCode.TOO_LARGE)
            else:
                relay.body += piece.data
                relay.next_seq += 1
            relay.changed.notify_all()
        return None

    def credit(self, envelope: protocol.Envelope) -> None:
        """``relay_credit``: the hub forwarded ``chunks`` more frames."""
        given = sessionwire.read_relay_credit(envelope)
        with self._lock:
            relay = self._active.get(given.request_id)
        if relay is not None:
            with relay.changed:
                relay.credit = min(relay.credit + given.chunks, relay.asked.window)
                relay.changed.notify_all()

    def cancel(self, envelope: protocol.Envelope) -> None:
        """``relay_cancel``: end the relay, hanging up on the head. A head's
        relay first reads what the head made (:meth:`_leave`), on a thread of
        its own: this one hears the hub and sends every frame, and waits for
        no page."""
        asked = sessionwire.read_relay_cancel(envelope)
        with self._lock:
            relay = self._active.get(asked.request_id)
        if relay is None:
            return
        if isinstance(relay.asked, sessionwire.RelayRequest):
            threading.Thread(
                target=self._leave, args=(relay,), name="mcgyvr-relay", daemon=True
            ).start()
        else:
            self._stop(relay, "cancelled", SessionCode.CANCELLED)

    def _leave(self, relay: _Relay) -> None:
        """End ``relay`` as cancelled, with what its head made by now when
        that can be told for certain."""
        try:
            made = self._made(relay)
            with relay.changed:
                if relay.outcome is None:
                    relay.made = made
        finally:  # whatever became of the reading, the relay ends
            self._stop(relay, "cancelled", SessionCode.CANCELLED)

    def _alone(self, relay: _Relay) -> int | None:
        """How many relays ever began, when ``relay`` is the only one in its
        head and the head is working on it; else ``None``."""
        with self._lock:
            others = any(
                other is not relay and other.target == relay.target
                for other in self._active.values()
            )
            begun = self._begun
        with relay.changed:
            working = relay.working and relay.outcome is None
        return begun if working and not others else None

    def _made(self, relay: _Relay) -> tuple[int, int] | None:
        """What ``relay``'s head made of it so far, by the head's own count,
        or ``None`` when that is not certain.

        The page lists the slots, not whose request each serves. The one slot
        at work is this relay's only if nothing else is in the head: this
        relay is alone in it, before the page is read and after, no relay
        began meanwhile, and the head is still working on it (its request is
        in, and its answer has not ended, or, not streamed, not begun: a slot
        whose answer is given is free, and counts nothing). The head's API
        is on this machine's loopback alone and the agent is the only way
        in, so then the slot is this relay's. A ride's unit is its host's
        too, and is never read."""
        begun = self._alone(relay)
        if begun is None:
            return None
        made = slot_made(_page(relay.target))
        return made if self._alone(relay) == begun else None

    def session_ended(self, session_id: str) -> None:
        """End every relay of ``session_id``: its head is gone. A ride is no
        session's, and goes on."""
        with self._lock:
            ending = [
                r
                for r in self._active.values()
                if isinstance(r.asked, sessionwire.RelayRequest)
                and r.asked.session_id == session_id
            ]
        for relay in ending:
            self._stop(relay, "cancelled", SessionCode.CANCELLED)

    def cancel_all(self) -> None:
        """End every relay: the hub that asked for them is gone."""
        with self._lock:
            ending = list(self._active.values())
        for relay in ending:
            self._stop(relay, "cancelled", SessionCode.CANCELLED)

    # -- the relay's thread --------------------------------------------------

    @staticmethod
    def _unread(envelope: protocol.Envelope) -> str | None:
        """The ``relay_end`` of a relay or a ride whose request does not read,
        when its id does; ``None`` when not even that reads."""
        request_id = envelope.body.get("request_id")
        if isinstance(request_id, str) and protocol.MESSAGE_ID.fullmatch(request_id):
            return sessionwire.relay_end(
                request_id, outcome="error", error_code=ErrorCode.BAD_MESSAGE
            )
        return None

    def _remember(self, request_id: str) -> None:
        if len(self._used) == self._used.maxlen:
            self._used_set.discard(self._used[0])
        self._used.append(request_id)
        self._used_set.add(request_id)

    def _why_not(self, session_id: str) -> str:
        state, role = self._heads.state_of(session_id)
        if state == "absent":
            return SessionCode.UNKNOWN_SESSION
        if role != "head":
            return SessionCode.NOT_CAPABLE
        return SessionCode.NOT_READY

    @staticmethod
    def _decide(relay: _Relay, outcome: str, code: str | None) -> bool:
        """Settle why ``relay`` ends, unless that is settled; whether it was not."""
        if relay.outcome is not None:
            return False
        relay.outcome = outcome
        relay.code = code
        return True

    def _stop(self, relay: _Relay, outcome: str, code: str | None) -> None:
        with relay.changed:
            self._decide(relay, outcome, code)
            connection = relay.connection
            relay.changed.notify_all()
        _hang_up(connection)

    def _end(self, relay: _Relay) -> None:
        with relay.changed:
            if relay.ended:
                return
            relay.ended = True
            outcome = relay.outcome or "complete"
            code = relay.code
            made = relay.made if outcome == "cancelled" else None
        with self._lock:
            self._active.pop(relay.asked.request_id, None)
        self._send(
            sessionwire.relay_end(
                relay.asked.request_id, outcome=outcome, error_code=code, made=made
            ),
            timeout=SEND_WAIT_S,
        )

    def _left(self, relay: _Relay) -> float:
        return relay.deadline - self._clock()

    def _expire(self, relay: _Relay) -> None:
        self._stop(relay, "timeout", ErrorCode.TIMEOUT)

    def _run(self, relay: _Relay) -> None:
        timer = threading.Timer(max(0.0, self._left(relay)), self._expire, (relay,))
        timer.daemon = True
        timer.start()
        try:
            with relay.admit():
                self._relay(relay)
        except RideRefusedError as refused:
            with relay.changed:
                self._decide(relay, "error", refused.code)
        except (OSError, http.client.HTTPException, ValueError):
            with relay.changed:
                self._decide(relay, "error", SessionCode.UPSTREAM_FAILED)
        finally:
            timer.cancel()
            with relay.changed:
                connection, relay.connection = relay.connection, None
            if connection is not None:
                with contextlib.suppress(OSError):
                    connection.close()
            self._end(relay)

    def _relay(self, relay: _Relay) -> None:
        with relay.changed:
            while relay.outcome is None and not relay.complete:
                relay.changed.wait(max(0.0, self._left(relay)))
            if relay.outcome is not None:
                return
            body = bytes(relay.body)
            connection = relay.target.connect(max(0.001, self._left(relay)))
            relay.connection = connection
        connection.request(
            "POST",
            relay.target.path,
            body=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream"
                if relay.asked.stream
                else "application/json",
            },
        )
        with relay.changed:
            if relay.outcome is not None:
                return
            relay.working = True
        try:
            self._answer(relay, connection)
        finally:
            with relay.changed:
                relay.working = False

    def _answer(self, relay: _Relay, connection: http.client.HTTPConnection) -> None:
        """The head's answer to the request it has, back to the hub."""
        response = connection.getresponse()
        if not relay.asked.stream:
            # Not streamed, the answer comes whole: the head has made it.
            with relay.changed:
                relay.working = False
        kind = response.getheader("Content-Type", "") or ""
        if len(
            kind
        ) > sessionwire.MAX_CONTENT_TYPE or not sessionwire.CONTENT_TYPE.fullmatch(
            kind
        ):
            kind = "application/octet-stream"
        if relay.outcome is not None:
            return
        if not self._send(
            sessionwire.relay_response(
                relay.asked.request_id, status=response.status, content_type=kind
            ),
            timeout=SEND_WAIT_S,
        ):
            self._stop(relay, "cancelled", SessionCode.CANCELLED)
            return
        sent = 0
        limit = sessionwire.RELAY_MAX_CHUNK_BYTES
        while True:
            with relay.changed:
                # A full frame waits its turn: the head's socket holds the rest.
                while relay.outcome is None and len(relay.pending) >= limit:
                    relay.changed.wait(max(0.0, self._left(relay)))
                if relay.outcome is not None:
                    return
                room = limit - len(relay.pending)
            chunk = response.read1(room)
            if not chunk:
                return
            if sent + len(chunk) > relay.asked.max_response_bytes:
                self._stop(relay, "too_large", SessionCode.TOO_LARGE)
                return
            sent += len(chunk)
            with relay.changed:
                relay.pending += chunk
                if relay.queued:  # the frame that waits carries this too
                    continue
                while relay.outcome is None and relay.credit <= 0:
                    relay.changed.wait(max(0.0, self._left(relay)))
                if relay.outcome is not None:
                    return
                relay.credit -= 1
                relay.queued = True
            if not self._send(lambda: self._data(relay), timeout=SEND_WAIT_S):
                self._stop(relay, "cancelled", SessionCode.CANCELLED)
                return

    @staticmethod
    def _data(relay: _Relay) -> str:
        """The frame of ``relay``'s answer that waits, made as the agent
        takes it to send: all that was read and is in no frame yet."""
        with relay.changed:
            data, relay.pending = bytes(relay.pending), bytearray()
            seq, relay.seq = relay.seq, relay.seq + 1
            relay.queued = False
            relay.changed.notify_all()
        return sessionwire.relay_data(relay.asked.request_id, seq=seq, data=data)


def slot_made(page: bytes | None) -> tuple[int, int] | None:
    """The counts of the one slot at work on llama.cpp's ``/slots`` page: the
    prompt's tokens and the tokens generated so far. ``None`` for anything
    else: no page, a page that is not a list of slots each saying whether it
    is at work, none or several at work, a count that is missing, no whole
    number, out of bounds, or a prompt not counted yet."""
    if page is None:
        return None
    try:
        slots = json.loads(page)
    except (ValueError, RecursionError):
        return None
    if not isinstance(slots, list):
        return None
    at_work = []
    for slot in slots:
        working = slot.get("is_processing") if isinstance(slot, dict) else None
        if not isinstance(working, bool):
            return None
        if working:
            at_work.append(slot)
    if len(at_work) != 1:
        return None
    (slot,) = at_work
    # The slot's next token is an object, or (newer servers) a list of one.
    following = slot.get("next_token")
    if isinstance(following, list) and len(following) == 1:
        following = following[0]
    if not isinstance(following, dict):
        return None
    tokens_in = _count(slot.get("n_prompt_tokens"))
    tokens_out = _count(following.get("n_decoded"))
    if not tokens_in or tokens_out is None:
        return None
    return tokens_in, tokens_out


def _count(value: object) -> int | None:
    """``value`` as a count a ``relay_end`` may carry, or ``None``."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 <= value <= sessionwire.RELAY_MAX_TOKENS else None


def _page(target: Target) -> bytes | None:
    """The status page of the server at ``target``, or ``None``: it has
    none, did not answer in :data:`REPORT_WAIT_S`, or sent too much."""
    try:
        connection = target.connect(REPORT_WAIT_S)
    except (OSError, ValueError):
        return None
    try:
        connection.request("GET", SLOTS_PATH, headers={"Accept": "application/json"})
        response = connection.getresponse()
        if response.status != 200:
            return None
        page = response.read(MAX_PAGE_BYTES + 1)
    except (OSError, http.client.HTTPException, ValueError):
        return None
    finally:
        with contextlib.suppress(OSError):
            connection.close()
    return page if len(page) <= MAX_PAGE_BYTES else None


def _hang_up(connection: http.client.HTTPConnection | None) -> None:
    """Shut ``connection``'s socket down under the relay reading it, which
    then ends and closes it: the head sees the hang-up at once, and the
    connection is never closed from two threads."""
    if connection is None:
        return
    sock = connection.sock
    if sock is not None:
        with contextlib.suppress(OSError):
            sock.shutdown(socket.SHUT_RDWR)


def register(dispatcher: commands.Dispatcher, relays: Relays) -> None:
    """Handle the hub's relay messages with ``relays``."""
    dispatcher.register("relay_request", lambda envelope, _: relays.request(envelope))
    dispatcher.register(
        "unit_relay_request", lambda envelope, _: relays.unit_request(envelope)
    )
    dispatcher.register("relay_data", lambda envelope, _: relays.data(envelope))

    def credit(envelope: protocol.Envelope, _: commands.Session) -> None:
        relays.credit(envelope)

    def cancel(envelope: protocol.Envelope, _: commands.Session) -> None:
        relays.cancel(envelope)

    dispatcher.register("relay_credit", credit)
    dispatcher.register("relay_cancel", cancel)
