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
  the relay stops reading the head, and the head's own socket holds it;
* exactly one ``relay_end`` — ``complete``; ``cancelled`` on the hub's
  ``relay_cancel`` or when the session ends; ``timeout`` past the hub's time;
  ``too_large`` past its size; or ``error`` with the hub's code.

A head serves as many requests at once as it has slots (``head_start``'s
``slots``), so a session takes at most that many relays at once, and the
next is answered ``busy`` without reaching the head. :data:`MAX_ACTIVE`
bounds the relays of the whole rig besides: a rig is in one session at a
time, so it is never below what that session's head may take.

A cancel or a deadline hangs up on the head, which stops generating. What a
relay carries is the users' and is never printed or put in a message: a
failure says only its class.
"""

from __future__ import annotations

import contextlib
import http.client
import socket
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from mcgyvr.rig import commands, protocol, sessionwire
from mcgyvr.rig.protocol import ErrorCode, ProtocolError
from mcgyvr.rig.sessionwire import SessionCode

#: How many relays may run at once on one rig, whatever its sessions: a
#: safety net under each head's own bound (its slots). A rig is in one
#: session at a time, so this is the most slots one head may have.
MAX_ACTIVE = sessionwire.MAX_SLOTS
#: How many request ids are remembered, so one is never used twice.
REMEMBERED_IDS = 4096
#: The longest a frame of the answer waits for the outbox, in seconds.
SEND_WAIT_S = 30.0


class Heads(Protocol):
    """Where a session's head is: :class:`mcgyvr.rig.session.Sessions`."""

    def head_port(self, session_id: str) -> int | None: ...

    def head_slots(self, session_id: str) -> int: ...

    def state_of(self, session_id: str) -> tuple[str, str | None]: ...


@dataclass(eq=False)
class _Relay:
    asked: sessionwire.RelayRequest
    port: int
    body: bytearray = field(default_factory=bytearray)
    next_seq: int = 0
    credit: int = 0
    outcome: str | None = None  # why it ends early, once decided
    code: str | None = None
    ended: bool = False
    changed: threading.Condition = field(default_factory=threading.Condition)
    connection: http.client.HTTPConnection | None = None
    deadline: float = 0.0

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
    ) -> None:
        self._heads = heads
        self._send = send
        self._max_active = max_active
        self._clock = clock
        self._lock = threading.Lock()
        self._active: dict[str, _Relay] = {}
        self._used: deque[str] = deque(maxlen=REMEMBERED_IDS)
        self._used_set: set[str] = set()

    # -- the handlers --------------------------------------------------------

    def request(self, envelope: protocol.Envelope) -> str | None:
        """``relay_request``: every one is answered with one ``relay_end``."""
        try:
            asked = sessionwire.read_relay_request(envelope)
        except ProtocolError:
            request_id = envelope.body.get("request_id")
            if isinstance(request_id, str) and protocol.MESSAGE_ID.fullmatch(
                request_id
            ):
                return sessionwire.relay_end(
                    request_id, outcome="error", error_code=ErrorCode.BAD_MESSAGE
                )
            raise
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
                if running.asked.session_id == asked.session_id
            )
            if (
                taken >= self._heads.head_slots(asked.session_id)
                or len(self._active) >= self._max_active
            ):
                return sessionwire.relay_end(
                    asked.request_id, outcome="error", error_code=SessionCode.BUSY
                )
            relay = _Relay(
                asked=asked,
                port=port,
                credit=asked.window,
                deadline=self._clock() + asked.timeout_s,
            )
            self._active[asked.request_id] = relay
        threading.Thread(target=self._run, args=(relay,), daemon=True).start()
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
        """``relay_cancel``: end the relay, hanging up on the head."""
        asked = sessionwire.read_relay_cancel(envelope)
        with self._lock:
            relay = self._active.get(asked.request_id)
        if relay is not None:
            self._stop(relay, "cancelled", SessionCode.CANCELLED)

    def session_ended(self, session_id: str) -> None:
        """End every relay of ``session_id``: its head is gone."""
        with self._lock:
            ending = [
                r for r in self._active.values() if r.asked.session_id == session_id
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
        with self._lock:
            self._active.pop(relay.asked.request_id, None)
        self._send(
            sessionwire.relay_end(
                relay.asked.request_id, outcome=outcome, error_code=code
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
            self._relay(relay)
        except (OSError, http.client.HTTPException, ValueError):
            with relay.changed:
                self._decide(relay, "error", SessionCode.UPSTREAM_FAILED)
        finally:
            timer.cancel()
            with relay.changed:
                connection, relay.connection = relay.connection, None
            _hang_up(connection)
            self._end(relay)

    def _relay(self, relay: _Relay) -> None:
        with relay.changed:
            while relay.outcome is None and not relay.complete:
                relay.changed.wait(max(0.0, self._left(relay)))
            if relay.outcome is not None:
                return
            body = bytes(relay.body)
            connection = http.client.HTTPConnection(
                "127.0.0.1", relay.port, timeout=max(0.001, self._left(relay))
            )
            relay.connection = connection
        connection.request(
            "POST",
            sessionwire.RELAY_PATHS[relay.asked.endpoint],
            body=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream"
                if relay.asked.stream
                else "application/json",
            },
        )
        if relay.outcome is not None:
            return
        response = connection.getresponse()
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
        seq = 0
        while relay.outcome is None:
            chunk = response.read1(sessionwire.RELAY_MAX_CHUNK_BYTES)
            if not chunk:
                return
            if sent + len(chunk) > relay.asked.max_response_bytes:
                self._stop(relay, "too_large", SessionCode.TOO_LARGE)
                return
            with relay.changed:
                while relay.outcome is None and relay.credit <= 0:
                    relay.changed.wait(max(0.0, self._left(relay)))
                if relay.outcome is not None:
                    return
                relay.credit -= 1
            if not self._send(
                sessionwire.relay_data(relay.asked.request_id, seq=seq, data=chunk),
                timeout=SEND_WAIT_S,
            ):
                self._stop(relay, "cancelled", SessionCode.CANCELLED)
                return
            sent += len(chunk)
            seq += 1


def _hang_up(connection: http.client.HTTPConnection | None) -> None:
    """Close ``connection``'s socket under whoever is reading it."""
    if connection is None:
        return
    sock = connection.sock
    if sock is not None:
        with contextlib.suppress(OSError):
            sock.shutdown(socket.SHUT_RDWR)
    with contextlib.suppress(OSError):
        connection.close()


def register(dispatcher: commands.Dispatcher, relays: Relays) -> None:
    """Handle the hub's relay messages with ``relays``."""
    dispatcher.register("relay_request", lambda envelope, _: relays.request(envelope))
    dispatcher.register("relay_data", lambda envelope, _: relays.data(envelope))

    def credit(envelope: protocol.Envelope, _: commands.Session) -> None:
        relays.credit(envelope)

    def cancel(envelope: protocol.Envelope, _: commands.Session) -> None:
        relays.cancel(envelope)

    dispatcher.register("relay_credit", credit)
    dispatcher.register("relay_cancel", cancel)
