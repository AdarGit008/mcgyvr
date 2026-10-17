"""Relay one OpenAI-protocol request from the hub to the server that runs it.

A ``relay_request`` names a session of this rig and a ``unit_relay_request`` a
unit the rig shares with riders. Either way the hub sends the request body in
``relay_data`` frames of its own, and this module posts it to the one address
that serves it — the head session's API on loopback, or the shared unit's
advertised URL, each at the path the endpoint names — then streams the answer
back as one ``relay_response``, ``relay_data`` frames within the credit the hub
grants, and exactly one ``relay_end``.

Each relay runs on a thread of its own: it waits for the body, posts it, reads
the answer, and ends with its outcome — ``complete``, ``cancelled`` on the
hub's word or on a channel that takes no more frames, ``timeout`` at the
request's deadline, or ``error`` with a code. What this rig cannot serve is
refused in the frame that ends the relay rather than started: a request id
used before, a session with no ready head, a unit not advertised, a rig
already as wide as it goes. A relay holds at most one chunk of the answer
beyond what has gone out, and waits for credit before it sends another.
"""

from __future__ import annotations

import contextlib
import http.client
import io
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

from mcgyvr import whole
from mcgyvr.rig import commands, protocol, sessionwire
from mcgyvr.rig.protocol import ErrorCode, ProtocolError
from mcgyvr.rig.sessionwire import SessionCode

# The default cap on the relays this rig runs at once. A session's relays are
# held to its head's slot count or this, whichever is lower; the rides on all
# of the rig's shared units together are held to this. Past either, the hub is
# answered ``busy`` in the frame that ends the relay, never queued behind it:
# every relay is a thread and a connection to a server already at work.
MAX_ACTIVE = sessionwire.MAX_SLOTS
# How many request ids last taken are remembered, so a hub that repeats one is
# told ``duplicate`` rather than given a second relay of the same id.
REMEMBERED_IDS = 4096
# Seconds one frame of a relay may wait for room in the channel before the
# relay counts as cancelled: the hub is gone or too far behind to answer.
SEND_WAIT_S = 30.0
# The path of the status page on which a head reports each of its slots: read
# on the API the relay posts to, and only to say what a leave had made.
SLOTS_PATH = "/slots"
# Seconds that page has to connect and arrive, on a thread of the relay's own,
# so that a leave is never held up by a head that does not answer.
REPORT_WAIT_S = 1.0
# The most the page may be; a longer one is read as no page at all.
MAX_PAGE_BYTES = 1 << 20


class Heads(Protocol):
    """The sessions this rig runs, asked about the heads among them.

    ``head_port`` gives the loopback port of a session whose head is ready to take
    a request, and ``None`` when it is not; ``head_slots`` the slots that head was
    asked for; ``state_of`` its state and role, which name the code a refused
    relay ends with.
    """

    def head_port(self, session_id: str) -> int | None: ...

    def head_slots(self, session_id: str) -> int: ...

    def state_of(self, session_id: str) -> tuple[str, str | None]: ...


class RideRefusedError(Exception):
    """A shared unit would not take the ride it was asked for.

    ``code`` is the code the relay ends with: the unit is not advertised, or it has
    no room left under its rider cap or its own free slots.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class Ride(Protocol):
    """A shared unit as it is advertised to riders: how many may ride at once, and
    the address a ride's request is posted to."""

    @property
    def rider_cap(self) -> int: ...

    def url(self, endpoint: str) -> str: ...


class Units(Protocol):
    """The units this rig shares with other rigs' riders.

    ``advertised`` names one as it stands now, or ``None`` when it is not shared;
    ``ride`` is entered around the posting of a ride's request and holds the unit's
    room meanwhile, raising :class:`RideRefusedError` when there is none.
    """

    def advertised(self, unit_id: str) -> Ride | None: ...

    def ride(self, unit_id: str) -> AbstractContextManager[None]: ...


@dataclass(frozen=True)
class Target:
    """Where one relayed request is posted: one host, one port, one path."""

    host: str
    port: int
    path: str
    tls: bool = False

    @classmethod
    def loopback(cls, port: int, endpoint: str) -> Target:
        """A head's API on this rig's own loopback, at the path the endpoint names."""
        return cls("127.0.0.1", port, sessionwire.RELAY_PATHS[endpoint])

    @classmethod
    def of_url(cls, url: str) -> Target:
        """A URL that a unit advertises, as a target to post to.

        Only an http(s) URL with a host is taken; a port left out defaults by scheme
        and a path left out to ``/``. A URL of any other shape is a ``ValueError``.
        """
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
    outcome: str | None = None  # the wire outcome, None while running
    code: str | None = None
    ended: bool = False
    changed: threading.Condition = field(default_factory=threading.Condition)
    connection: http.client.HTTPConnection | None = None
    deadline: float = 0.0
    working: bool = False  # request posted, its answer not in hand
    made: tuple[int, int] | None = None  # tokens in and out at a leave
    pending: bytearray = field(default_factory=bytearray)  # bytes read, no frame yet
    queued: bool = False  # its frame waits to be sent
    seq: int = 0  # seq of the next relay_data frame

    @property
    def complete(self) -> bool:
        return len(self.body) == self.asked.body_bytes


class Relays:
    """The relays this rig runs, one per request the hub sends it to serve.

    Each is begun by :meth:`request` for a session of this rig or
    :meth:`unit_request` for a ride on a shared unit, and runs on a thread of its
    own: it waits for the body, posts it to the one address that serves it, sends
    the answer back within the hub's credit, and ends with exactly one
    ``relay_end``. The frames of a relay already running — more body, credit, a
    cancel — are taken by :meth:`data`, :meth:`credit` and :meth:`cancel`, and a
    session that ends or a rig going away ends its relays through
    :meth:`session_ended` and :meth:`cancel_all`.
    """

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
        self._begun = 0  # every relay begun, for the page check
        self._used: deque[str] = deque(maxlen=REMEMBERED_IDS)
        self._used_set: set[str] = set()

    # The hub's frames of a relay: begin one, or feed one already begun.

    def request(self, envelope: protocol.Envelope) -> str | None:
        """A session's relay, begun or refused.

        The body is read off the envelope, and its request id remembered, so that a
        repeat of it is answered ``duplicate``. A session with no ready head is
        refused with the code its state and role give, and one already holding as many
        relays as its head's slots or the rig's width allow with ``busy``. Otherwise a
        thread posts the request to the head's loopback API at the endpoint's path.

        The answer is a frame the caller must send, or ``None`` when the relay runs. A
        body that cannot be read is answered ``BAD_MESSAGE`` when it still carries a
        request id, and raises otherwise.
        """
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
        """A ride's relay, begun or refused.

        As :meth:`request`, but the unit must be advertised now: one that is not is
        refused ``unknown_unit``. Its advertised rider cap, and the rig's width over
        all its rides, refuse ``busy`` here; the unit's own free slots are weighed
        when the ride is taken on the relay's thread, and a refusal there ends the
        relay ``busy`` too. The request is posted to the address the unit advertises
        at the endpoint's path, and an address that is no http(s) URL is refused
        ``upstream_failed``.
        """
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
        """One chunk of a relay's request body, in the order the hub counted it.

        A chunk out of that order, or one that would carry the body past the length
        the request announced, ends the relay there — ``BAD_MESSAGE`` or
        ``too_large``. A chunk of a relay that has ended already, or whose body is
        whole, is ignored, so nothing is read past the end of the body. A request id
        of no relay this rig is serving is refused instead.
        """
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
        """The hub grants room for more frames of a relay's answer.

        The chunks are added to what the relay may still send, never above the window
        the request asked for. A request id of no relay now running is ignored.
        """
        given = sessionwire.read_relay_credit(envelope)
        with self._lock:
            relay = self._active.get(given.request_id)
        if relay is not None:
            with relay.changed:
                relay.credit = min(relay.credit + given.chunks, relay.asked.window)
                relay.changed.notify_all()

    def cancel(self, envelope: protocol.Envelope) -> None:
        """The hub has left a relay, which is ended as cancelled on a thread of its own.

        That thread reads what the head's slot had made before hanging up, so the
        thread that hears the hub never waits on a head.
        """
        asked = sessionwire.read_relay_cancel(envelope)
        with self._lock:
            relay = self._active.get(asked.request_id)
        if relay is None:
            return
        threading.Thread(
            target=self._leave, args=(relay,), name="mcgyvr-relay", daemon=True
        ).start()

    def _leave(self, relay: _Relay) -> None:
        """Read what the head made for a leaving relay, then end it cancelled.

        The counts are kept only if no outcome is settled by the time they are in
        hand, so an outcome settled first — a timeout, an answer, a failure — is not
        overwritten by the leave.
        """
        try:
            made = self._made(relay)
            with relay.changed:
                if relay.outcome is None:
                    relay.made = made
        finally:  # here the relay ends, page read or not
            self._stop(relay, "cancelled", SessionCode.CANCELLED)

    def _alone(self, relay: _Relay) -> int | None:
        """The count of relays begun so far, when the head is this relay's alone.

        Which is when this is the only relay on its target and the head is still
        working on it; ``None`` otherwise, or once the relay has ended. The count is
        what :meth:`_made` compares before and after the page to tell whether another
        relay began while it was being read.
        """
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
        """What the head's one working slot had made: tokens in and out, or ``None``.

        No page is read unless what it says can only be this relay's slot's:
        :meth:`_alone` must answer, and answer the same before and after the read,
        since a page does not say which relay a busy slot is serving.
        """
        begun = self._alone(relay)
        if begun is None:
            return None
        made = slot_made(_page(relay.target))
        return made if self._alone(relay) == begun else None

    def session_ended(self, session_id: str) -> None:
        """Every relay of a session that has ended is ended as cancelled, at once.

        The head is not read for these, and rides on shared units are not the
        session's to end.
        """
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
        """Every relay this rig runs is ended as cancelled at once, the heads unread.

        Used when the rig goes offline or closes, when no answer can be delivered any
        more.
        """
        with self._lock:
            ending = list(self._active.values())
        for relay in ending:
            self._stop(relay, "cancelled", SessionCode.CANCELLED)

    # The private side: reading what the hub sent, deciding and ending.

    @staticmethod
    def _unread(envelope: protocol.Envelope) -> str | None:
        """The frame refusing a request whose body could not be read, or ``None``.

        A body that still carries a well-formed request id is one the hub can be told
        about, so its relay is ended ``BAD_MESSAGE`` at once; a body without one leaves
        the caller to raise, as there is nothing to name it by.
        """
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
        """Settle a relay's outcome, unless one is settled already.

        Returns whether this call was the one that settled it, so that the first
        outcome decided — a cancel from the hub, a timeout, a failure — is the one the
        relay ends with.
        """
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
        # A requester who asked for one body is served the same way: the head is asked
        # to stream and the events are joined here, so a requester who leaves stops the
        # head's slot at its next write, not at the end of an answer nobody waits for.
        # A body `as_stream` will not rewrite — no JSON object, or text UTF-8 cannot
        # carry — is posted as it came.
        assembly = None
        if not relay.asked.stream:
            streamed = whole.as_stream(body)
            if streamed is not None:
                body, assembly = streamed, whole.Whole()
        connection.request(
            "POST",
            relay.target.path,
            body=body,
            headers={
                "Content-Type": "application/json",
                "Accept": whole.EVENT_STREAM
                if relay.asked.stream or assembly is not None
                else "application/json",
            },
        )
        with relay.changed:
            if relay.outcome is not None:
                return
            relay.working = True
        try:
            self._answer(relay, connection, assembly)
        finally:
            with relay.changed:
                relay.working = False

    def _answer(
        self,
        relay: _Relay,
        connection: http.client.HTTPConnection,
        assembly: whole.Whole | None,
    ) -> None:
        """Send the head's answer back: its status and content type, then its body.

        The content type is taken only in the shape the wire carries, and anything else
        goes as ``application/octet-stream``. A streamed answer that was asked for as
        one body is assembled first and sent whole; a head that answers such a request
        with another status, or with no stream, is passed through as it answered. Every
        chunk is checked against the length the request allowed, and no chunk is read
        while the frame before it waits for the hub's credit.
        """
        response = connection.getresponse()
        status = response.status
        kind = response.getheader("Content-Type", "") or ""
        if len(
            kind
        ) > sessionwire.MAX_CONTENT_TYPE or not sessionwire.CONTENT_TYPE.fullmatch(
            kind
        ):
            kind = "application/octet-stream"
        source: io.BufferedIOBase = response
        streamed = whole.media(kind) == whole.EVENT_STREAM
        if assembly is not None and status == 200 and streamed:
            answer = self._assemble(relay, response, assembly)
            if answer is None:
                return
            status, kind, body = answer
            source = io.BytesIO(body)
        if not relay.asked.stream:
            # The whole answer is in hand, so the head is no longer at work on it:
            # a leave from here on has no page worth reading.
            with relay.changed:
                relay.working = False
        if relay.outcome is not None:
            return
        if not self._send(
            sessionwire.relay_response(
                relay.asked.request_id, status=status, content_type=kind
            ),
            timeout=SEND_WAIT_S,
        ):
            self._stop(relay, "cancelled", SessionCode.CANCELLED)
            return
        sent = 0
        limit = sessionwire.RELAY_MAX_CHUNK_BYTES
        while True:
            with relay.changed:
                # One frame of the answer at a time: the next chunk is read only once
                # the frame of the last one has been sent.
                while relay.outcome is None and len(relay.pending) >= limit:
                    relay.changed.wait(max(0.0, self._left(relay)))
                if relay.outcome is not None:
                    return
                room = limit - len(relay.pending)
            chunk = source.read1(room)
            if not chunk:
                return
            if sent + len(chunk) > relay.asked.max_response_bytes:
                self._stop(relay, "too_large", SessionCode.TOO_LARGE)
                return
            sent += len(chunk)
            with relay.changed:
                relay.pending += chunk
                if relay.queued:  # a frame is already going out
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
        """The next frame of the answer, made as the channel takes it.

        The bytes read since the last frame go out as one ``relay_data`` under the next
        seq, and the reader waiting for room is woken. Being made late is the point: a
        frame carries whatever the head had written by the time it is sent, so the
        agent's frame rate is not a cap on tokens.
        """
        with relay.changed:
            data, relay.pending = bytes(relay.pending), bytearray()
            seq, relay.seq = relay.seq, relay.seq + 1
            relay.queued = False
            relay.changed.notify_all()
        return sessionwire.relay_data(relay.asked.request_id, seq=seq, data=data)

    def _assemble(
        self,
        relay: _Relay,
        response: http.client.HTTPResponse,
        assembly: whole.Whole,
    ) -> tuple[int, str, bytes] | None:
        """Join a streamed answer into the one body it was asked for.

        The stream is read a chunk at a time into ``assembly``, which counts the text
        and logprobs it holds; that count running past the length the request allowed
        ends the relay ``too_large``, as does an assembled body that is too long. An
        assembly that never completes — no choice at all, or a choice the head never
        finished — ends it ``error`` against the upstream, and ``None`` comes back so
        that nothing more is sent. An error event inside the stream is no failure
        here: it is carried out as the error body the head would have answered with.
        """
        limit = relay.asked.max_response_bytes
        while True:
            with relay.changed:
                if relay.outcome is not None:
                    return None
            chunk = response.read1(sessionwire.RELAY_MAX_CHUNK_BYTES)
            if not chunk:
                break
            assembly.feed(chunk)
            if assembly.size > limit:
                self._stop(relay, "too_large", SessionCode.TOO_LARGE)
                return None
        answer = assembly.answer()
        if answer is None:
            self._stop(relay, "error", SessionCode.UPSTREAM_FAILED)
            return None
        if len(answer[2]) > limit:
            self._stop(relay, "too_large", SessionCode.TOO_LARGE)
            return None
        return answer


def slot_made(page: bytes | None) -> tuple[int, int] | None:
    """What a llama.cpp ``/slots`` page says its one working slot had made.

    The counts are tokens in and out: the prompt as the processed and cached
    prompt tokens, and the answer as the next token's ``n_decoded``. ``None``
    comes back unless the page is one whose counts can only be that slot's — a
    JSON list whose every entry says whether it is processing, exactly one of
    them busy, every count a number in bounds, a prompt of at least one token,
    and a context that is either the prompt or the prompt and the answer
    together, give or take the one token a read can land on.
    """
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
    # the last token's data is a list of one here, and one object elsewhere
    following = slot.get("next_token")
    if isinstance(following, list) and len(following) == 1:
        following = following[0]
    if not isinstance(following, dict):
        return None
    processed = _count(slot.get("n_prompt_tokens_processed"))
    cached = _count(slot.get("n_prompt_tokens_cache"))
    context = _count(slot.get("n_prompt_tokens"))
    tokens_out = _count(following.get("n_decoded"))
    if processed is None or cached is None or context is None or tokens_out is None:
        return None
    tokens_in = _count(processed + cached)
    if not tokens_in:
        return None
    if context != tokens_in and abs(context - (tokens_in + tokens_out)) > 1:
        return None
    return tokens_in, tokens_out


def _count(value: object) -> int | None:
    """A value of the page as a token count, or ``None`` when it is no count.

    A bool, no int at all, or a number outside the wire's bounds is no count.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 <= value <= sessionwire.RELAY_MAX_TOKENS else None


def _page(target: Target) -> bytes | None:
    """The ``/slots`` page of the server a relay posts to, or ``None``.

    Read over a connection of its own within ``REPORT_WAIT_S`` and at most
    ``MAX_PAGE_BYTES``: one that cannot be read whole — no connection, an answer
    of anything but 200, or a page longer than that — is no page.
    """
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
    """Shut the socket under a relay's request down, so a read on it fails now.

    Only the relay's own thread closes a connection it reads, since ``http.client``
    fails when one is closed from two threads at once; whoever stops a relay does
    this much and no more. There is nothing to do without a connection, or once
    its socket has gone.
    """
    if connection is None:
        return
    sock = connection.sock
    if sock is not None:
        with contextlib.suppress(OSError):
            sock.shutdown(socket.SHUT_RDWR)


def register(dispatcher: commands.Dispatcher, relays: Relays) -> None:
    """Answer the relay frames of the wire with the relays of this rig.

    ``relay_request``, ``unit_relay_request`` and ``relay_data`` may each answer
    with a frame the caller sends; ``relay_credit`` and ``relay_cancel`` answer
    nothing, since the relay's own thread is the one that ends it.
    """
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
