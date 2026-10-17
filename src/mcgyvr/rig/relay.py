""

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

#
#
#
#
#
MAX_ACTIVE = sessionwire.MAX_SLOTS
#
REMEMBERED_IDS = 4096
#
SEND_WAIT_S = 30.0
#
#
SLOTS_PATH = "/slots"
#
#
REPORT_WAIT_S = 1.0
#
MAX_PAGE_BYTES = 1 << 20


class Heads(Protocol):
    ""

    def head_port(self, session_id: str) -> int | None: ...

    def head_slots(self, session_id: str) -> int: ...

    def state_of(self, session_id: str) -> tuple[str, str | None]: ...


class RideRefusedError(Exception):
    ""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class Ride(Protocol):
    ""

    @property
    def rider_cap(self) -> int: ...

    def url(self, endpoint: str) -> str: ...


class Units(Protocol):
    ""

    def advertised(self, unit_id: str) -> Ride | None: ...

    def ride(self, unit_id: str) -> AbstractContextManager[None]: ...


@dataclass(frozen=True)
class Target:
    ""

    host: str
    port: int
    path: str
    tls: bool = False

    @classmethod
    def loopback(cls, port: int, endpoint: str) -> Target:
        ""
        return cls("127.0.0.1", port, sessionwire.RELAY_PATHS[endpoint])

    @classmethod
    def of_url(cls, url: str) -> Target:
        ""
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
    outcome: str | None = None  #
    code: str | None = None
    ended: bool = False
    changed: threading.Condition = field(default_factory=threading.Condition)
    connection: http.client.HTTPConnection | None = None
    deadline: float = 0.0
    working: bool = False  #
    made: tuple[int, int] | None = None  #
    pending: bytearray = field(default_factory=bytearray)  #
    queued: bool = False  #
    seq: int = 0  #

    @property
    def complete(self) -> bool:
        return len(self.body) == self.asked.body_bytes


class Relays:
    ""

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
        self._begun = 0  #
        self._used: deque[str] = deque(maxlen=REMEMBERED_IDS)
        self._used_set: set[str] = set()

    #

    def request(self, envelope: protocol.Envelope) -> str | None:
        ""
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
        ""
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
        ""
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
        ""
        given = sessionwire.read_relay_credit(envelope)
        with self._lock:
            relay = self._active.get(given.request_id)
        if relay is not None:
            with relay.changed:
                relay.credit = min(relay.credit + given.chunks, relay.asked.window)
                relay.changed.notify_all()

    def cancel(self, envelope: protocol.Envelope) -> None:
        ""
        asked = sessionwire.read_relay_cancel(envelope)
        with self._lock:
            relay = self._active.get(asked.request_id)
        if relay is None:
            return
        threading.Thread(
            target=self._leave, args=(relay,), name="mcgyvr-relay", daemon=True
        ).start()

    def _leave(self, relay: _Relay) -> None:
        ""
        try:
            made = self._made(relay)
            with relay.changed:
                if relay.outcome is None:
                    relay.made = made
        finally:  #
            self._stop(relay, "cancelled", SessionCode.CANCELLED)

    def _alone(self, relay: _Relay) -> int | None:
        ""
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
        ""
        begun = self._alone(relay)
        if begun is None:
            return None
        made = slot_made(_page(relay.target))
        return made if self._alone(relay) == begun else None

    def session_ended(self, session_id: str) -> None:
        ""
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
        ""
        with self._lock:
            ending = list(self._active.values())
        for relay in ending:
            self._stop(relay, "cancelled", SessionCode.CANCELLED)

    #

    @staticmethod
    def _unread(envelope: protocol.Envelope) -> str | None:
        ""
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
        ""
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
        #
        #
        #
        #
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
        ""
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
            #
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
                #
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
                if relay.queued:  #
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
        ""
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
        ""
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
    ""
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
    #
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
    ""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 <= value <= sessionwire.RELAY_MAX_TOKENS else None


def _page(target: Target) -> bytes | None:
    ""
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
    ""
    if connection is None:
        return
    sock = connection.sock
    if sock is not None:
        with contextlib.suppress(OSError):
            sock.shutdown(socket.SHUT_RDWR)


def register(dispatcher: commands.Dispatcher, relays: Relays) -> None:
    ""
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
