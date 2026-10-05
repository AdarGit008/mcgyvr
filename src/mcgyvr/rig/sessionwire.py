"""The session and relay messages of the hub's protocol v1, as the agent speaks them.

The hub's schema is the one definition (``tests/rig_schema.py`` pins it);
this module reads the commands the hub sends a rig that offered to lend
(``session_prepare``, ``tunnel_up``, ``worker_start``, ``head_start``,
``session_query``, ``session_stop``, ``relay_request``, ``relay_data``,
``relay_credit``, ``relay_cancel``, the latency probe's ``probe_open`` and
``probe_run``, and a ride to a shared unit, ``unit_relay_request``) and writes
the agent's side (``session_prepared``, ``session_status``,
``tunnel_report``, ``relay_response``, ``relay_data``, ``relay_end``,
``peer_rtt``, ``probe_opened``, ``probe_result``, and the shared units'
``unit_advert``).

Reading is the shape and the bounds the schema states, checked here with
nothing taken on trust: every field is read by name and type (a ``true`` is
not a number), every string whole against its pattern, every address as an
address, every list against its bounds and its uniqueness rule. A refusal is
:class:`mcgyvr.rig.protocol.ProtocolError` with ``bad_message`` naming the
field, never the value. What a valid command may *mean* on this rig (an
address it will not reach, a card it does not lend, a model it does not
have) is not read here; :mod:`mcgyvr.rig.tunnel` and :mod:`mcgyvr.rig.session`
decide that.
"""

from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from mcgyvr.rig import protocol
from mcgyvr.rig.protocol import ErrorCode, ProtocolError

#: The bounds the schema states, by name.
MAX_ENDPOINTS = protocol.MAX_ENDPOINTS
MAX_PEERS = 15
MAX_ALLOWED_IPS = 4
MAX_DEVICES = 64
MAX_RTT_SAMPLES = 32
MAX_RTT_US = 60_000_000
MAX_CTX = 1 << 20
MIN_CTX = 256
MAX_TENSOR_SHARE = 1 << 20
MAX_GPU_LAYERS = 4096
#: How many requests a head serves at once: ``head_start``'s ``slots``, each
#: with ``ctx`` of its own. The hub sends more than one only to an agent that
#: speaks the ``head_slots`` feature.
MAX_SLOTS = 16
DEFAULT_SLOTS = 1
#: The units a host shares with riders (hitchhike, the ``hitchhike_units``
#: feature): the most one ``unit_advert`` carries; how often, in seconds, the
#: agent sends one at least; and how old, in seconds, one is when the hub takes
#: it as withdrawn.
MAX_UNITS = 16
UNIT_ADVERT_INTERVAL_S = 60
UNIT_ADVERT_STALE_S = 180
MAX_KEEPALIVE_S = 600
DEFAULT_KEEPALIVE_S = 25
DEFAULT_GPU_LAYERS = 999
MAX_PORT = 65535
LOG_EXCERPT_MAX_CHARS = 4000
RELAY_MAX_CHUNK_BYTES = 32 * 1024
RELAY_MAX_REQUEST_BYTES = 1 << 20
RELAY_MAX_RESPONSE_BYTES = 64 << 20
RELAY_MAX_WINDOW = 64
RELAY_MAX_TIMEOUT_S = 3600
RELAY_MAX_SEQ = 1 << 31
MAX_CONTENT_TYPE = 128
#: The longest base64 text of one relay chunk.
RELAY_MAX_CHUNK_B64 = 4 * -(-RELAY_MAX_CHUNK_BYTES // 3)
#: The probe's and the traversal's bounds, and their defaults.
MAX_STUN_ENDPOINTS = 2
MIN_PROBE_TTL_S = 5
MAX_PROBE_TTL_S = 120
DEFAULT_PROBE_TTL_S = 30
MAX_PROBE_COUNT = 20
DEFAULT_PROBE_COUNT = 5
MIN_PROBE_INTERVAL_MS = 10
MAX_PROBE_INTERVAL_MS = 1000
DEFAULT_PROBE_INTERVAL_MS = 50
MAX_PROBE_BULK_BYTES = 256 * 1024
MIN_PROBE_DEADLINE_MS = 100
MAX_PROBE_DEADLINE_MS = 15_000
DEFAULT_PROBE_DEADLINE_MS = 5000
MAX_ATTEMPT_S = 30
MAX_CONNECT_TIMEOUT_S = 300
MAX_RATE_KBPS = 100_000_000
MAX_PCT = 100

#: The shapes of the wire's strings, matched whole.
SESSION_ID = protocol.MESSAGE_ID
MODEL_NAME = protocol.MODEL_NAME
DIGEST = protocol.DIGEST
HOST = protocol.ENDPOINT_HOST
WIREGUARD_KEY = re.compile(r"[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=")
IPV4 = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}")
IPV4_CIDR = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}")
CONTENT_TYPE = re.compile(
    r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+(; ?[A-Za-z0-9_-]+=[A-Za-z0-9_.-]+)?"
)
BASE64 = re.compile(r"[A-Za-z0-9+/]*={0,2}")
#: A token or a probe secret: 16 random bytes as 32 hex digits.
TOKEN = re.compile(r"[0-9a-f]{32}")
#: A relay ticket, opaque to the rig.
TICKET = re.compile(r"[A-Za-z0-9_-]{22,256}")

Role = Literal["head", "worker"]
ROLES = protocol.ROLES
#: The states a session is reported in, as the schema lists them.
STATES = (
    "absent",
    "preparing",
    "prepared",
    "tunnel_up",
    "starting",
    "loading",
    "ready",
    "failed",
    "stopped",
)
RELAY_OUTCOMES = ("complete", "error", "cancelled", "timeout", "too_large")
#: The relayed endpoints, and the head's path for each: the only paths the
#: agent ever asks the head for on a relay.
RELAY_PATHS = {"chat_completions": "/v1/chat/completions"}


class SessionCode:
    """The error codes of session and relay answers, as the hub names them."""

    BUSY = "busy"
    NOT_CAPABLE = "not_capable"
    UNKNOWN_SESSION = "unknown_session"
    MODEL_MISSING = "model_missing"
    INSUFFICIENT_MEMORY = "insufficient_memory"
    TUNNEL_FAILED = "tunnel_failed"
    START_FAILED = "start_failed"
    NOT_READY = "not_ready"
    DUPLICATE = "duplicate"
    UPSTREAM_FAILED = "upstream_failed"
    TOO_LARGE = "too_large"
    CANCELLED = "cancelled"
    MODEL_MISMATCH = "model_mismatch"
    NO_PATH = "no_path"
    UNKNOWN_UNIT = "unknown_unit"
    #: A head whose load stopped moving.
    LOAD_STALLED = "load_stalled"
    #: A peer whose last path answers a small ping and loses every full-size
    #: one.
    PATH_TOO_NARROW = "path_too_narrow"


# --- what the hub sends ----------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Endpoint:
    """A candidate address a tunnel is reached at."""

    host: str
    port: int
    kind: str


@dataclass(frozen=True, kw_only=True)
class Traversal:
    """Where a session's binding requests go, and the token they carry."""

    token: bytes
    stun: tuple[Endpoint, ...]


@dataclass(frozen=True, kw_only=True)
class SessionPrepare:
    session_id: str
    role: Role
    traversal: Traversal | None = None


@dataclass(frozen=True, kw_only=True)
class RelayGrant:
    """A relay this rig may fall back to for one peer; ``ticket`` is opaque."""

    host: str
    port: int
    ticket: str


@dataclass(frozen=True, kw_only=True)
class TunnelPeer:
    rig_id: str
    public_key: str
    endpoints: tuple[Endpoint, ...]
    allowed_ips: tuple[ipaddress.IPv4Network, ...]
    keepalive_s: int
    relay: RelayGrant | None = None


@dataclass(frozen=True, kw_only=True)
class TunnelUp:
    session_id: str
    address: ipaddress.IPv4Interface
    listen_port: int
    peers: tuple[TunnelPeer, ...]
    attempt_s: int | None = None
    connect_timeout_s: int | None = None


@dataclass(frozen=True, kw_only=True)
class ProbeOpen:
    probe_id: str
    token: bytes
    stun: tuple[Endpoint, ...]
    ttl_s: int


@dataclass(frozen=True, kw_only=True)
class ProbePeer:
    rig_id: str
    secret: bytes
    endpoints: tuple[Endpoint, ...]


@dataclass(frozen=True, kw_only=True)
class ProbeRun:
    probe_id: str
    peers: tuple[ProbePeer, ...]
    count: int
    interval_ms: int
    bulk_bytes: int
    deadline_ms: int


@dataclass(frozen=True, kw_only=True)
class WorkerCard:
    card_index: int
    port: int


@dataclass(frozen=True, kw_only=True)
class WorkerStart:
    session_id: str
    cards: tuple[WorkerCard, ...]


@dataclass(frozen=True, kw_only=True)
class LocalDevice:
    card_index: int


@dataclass(frozen=True, kw_only=True)
class RpcDevice:
    host: ipaddress.IPv4Address
    port: int


@dataclass(frozen=True, kw_only=True)
class HeadStart:
    session_id: str
    model: str
    digest: str | None
    ctx: int  # the context of one slot
    devices: tuple[LocalDevice | RpcDevice, ...]  # in the hub's order, kept
    tensor_split: tuple[int, ...]
    n_gpu_layers: int
    slots: int = DEFAULT_SLOTS


@dataclass(frozen=True, kw_only=True)
class SessionQuery:
    session_id: str


@dataclass(frozen=True, kw_only=True)
class SessionStop:
    session_id: str
    reason: str | None


@dataclass(frozen=True, kw_only=True)
class RelayRequest:
    session_id: str
    request_id: str
    endpoint: str
    body_bytes: int
    stream: bool
    timeout_s: int
    max_response_bytes: int
    window: int


@dataclass(frozen=True, kw_only=True)
class UnitRelayRequest:
    """A ride: a ``relay_request`` aimed at a unit this host shares, named by
    the ``unit_id`` its advert gave it, in place of a session."""

    unit_id: str
    request_id: str
    endpoint: str
    body_bytes: int
    stream: bool
    timeout_s: int
    max_response_bytes: int
    window: int


@dataclass(frozen=True, kw_only=True)
class RelayData:
    request_id: str
    seq: int
    data: bytes


@dataclass(frozen=True, kw_only=True)
class RelayCredit:
    request_id: str
    chunks: int


@dataclass(frozen=True, kw_only=True)
class RelayCancel:
    request_id: str
    reason: str | None


class _Body:
    """One body read field by field; a refusal names the field."""

    def __init__(self, body: Mapping[str, Any], at: str, re_id: str) -> None:
        self._body = body
        self._at = at
        self._re = re_id

    def refuse(self, field: str, why: str) -> ProtocolError:
        return ProtocolError(
            ErrorCode.BAD_MESSAGE, f"{self._at}.{field}: {why}", self._re
        )

    def has(self, field: str) -> bool:
        return self._body.get(field) is not None

    def raw(self, field: str) -> Any:
        return self._body.get(field)

    def text(
        self, field: str, shape: re.Pattern[str], *, optional: bool = False
    ) -> Any:
        value = self._body.get(field)
        if value is None and optional:
            return None
        if not isinstance(value, str) or not shape.fullmatch(value):
            raise self.refuse(field, "not of its shape")
        return value

    def number(
        self, field: str, low: int, high: int, *, default: int | None = None
    ) -> int:
        value = self._body.get(field)
        if value is None and default is not None:
            return default
        if type(value) is not int or not low <= value <= high:
            raise self.refuse(field, f"not a whole number of {low} to {high}")
        return value

    def flag(self, field: str) -> bool:
        value = self._body.get(field)
        if type(value) is not bool:
            raise self.refuse(field, "not true or false")
        return value

    def items(
        self, field: str, low: int, high: int, *, optional: bool = False
    ) -> list[Any]:
        value = self._body.get(field)
        if value is None and optional:
            value = []
        if not isinstance(value, list) or not low <= len(value) <= high:
            raise self.refuse(field, f"not a list of {low} to {high} items")
        return value

    def one_of(self, field: str, allowed: Sequence[str]) -> str:
        value = self._body.get(field)
        if not isinstance(value, str) or value not in allowed:
            raise self.refuse(field, f"not one of {', '.join(allowed)}")
        return value

    def nested(self, field: str, value: Any) -> _Body:
        if not isinstance(value, dict):
            raise self.refuse(field, "not an object")
        return _Body(value, f"{self._at}.{field}", self._re)


def _ipv4(text: str) -> ipaddress.IPv4Address | None:
    try:
        return ipaddress.IPv4Address(text)
    except ValueError:
        return None


def _cidr(text: str) -> ipaddress.IPv4Interface | None:
    try:
        return ipaddress.IPv4Interface(text)
    except ValueError:
        return None


def _unique(body: _Body, field: str, values: Sequence[object]) -> None:
    if len(set(values)) != len(values):
        raise body.refuse(field, "an entry twice")


def _endpoints(body: _Body, field: str) -> tuple[Endpoint, ...]:
    found = []
    for item in body.items(field, 0, MAX_ENDPOINTS, optional=True):
        entry = body.nested(field, item)
        found.append(
            Endpoint(
                host=entry.text("host", HOST),
                port=entry.number("port", 1, MAX_PORT),
                kind=entry.text("kind", protocol.TAG),
            )
        )
    return tuple(found)


def _slots(body: _Body) -> int:
    """``slots`` of ``body``: how many requests a unit serves at once, 1 to
    :data:`MAX_SLOTS`, :data:`DEFAULT_SLOTS` when it is left out. One reading
    for every message that carries it."""
    return body.number("slots", 1, MAX_SLOTS, default=DEFAULT_SLOTS)


def _start(envelope: protocol.Envelope) -> _Body:
    return _Body(envelope.body, "body", envelope.id)


def _token(body: _Body, field: str) -> bytes:
    return bytes.fromhex(body.text(field, TOKEN))


def read_session_prepare(envelope: protocol.Envelope) -> SessionPrepare:
    """The ``session_prepare`` in ``envelope``, or :class:`ProtocolError`."""
    body = _start(envelope)
    role = body.one_of("role", ROLES)
    traversal = None
    if body.has("traversal"):
        asked = body.nested("traversal", body.raw("traversal"))
        stun = _endpoints(asked, "stun")
        if not 1 <= len(stun) <= MAX_STUN_ENDPOINTS:
            raise asked.refuse("stun", f"not a list of 1 to {MAX_STUN_ENDPOINTS}")
        traversal = Traversal(token=_token(asked, "token"), stun=stun)
    return SessionPrepare(
        session_id=body.text("session_id", SESSION_ID),
        role="head" if role == "head" else "worker",
        traversal=traversal,
    )


def read_tunnel_up(envelope: protocol.Envelope) -> TunnelUp:
    """The ``tunnel_up`` in ``envelope``, or :class:`ProtocolError`."""
    body = _start(envelope)
    session_id = body.text("session_id", SESSION_ID)
    address = _cidr(body.text("address", IPV4_CIDR))
    if address is None:
        raise body.refuse("address", "not an address with its prefix")
    listen_port = body.number("listen_port", 1, MAX_PORT)
    peers = []
    for item in body.items("peers", 1, MAX_PEERS):
        peer = body.nested("peers", item)
        allowed = []
        for text in peer.items("allowed_ips", 1, MAX_ALLOWED_IPS):
            if not isinstance(text, str) or not IPV4_CIDR.fullmatch(text):
                raise peer.refuse("allowed_ips", "not an address with its prefix")
            net = _cidr(text)
            if net is None:
                raise peer.refuse("allowed_ips", "not an address with its prefix")
            allowed.append(net.network)
        relay = None
        if peer.has("relay"):
            grant = peer.nested("relay", peer.raw("relay"))
            relay = RelayGrant(
                host=grant.text("host", HOST),
                port=grant.number("port", 1, MAX_PORT),
                ticket=grant.text("ticket", TICKET),
            )
        peers.append(
            TunnelPeer(
                rig_id=peer.text("rig_id", protocol.MESSAGE_ID),
                public_key=peer.text("public_key", WIREGUARD_KEY),
                endpoints=_endpoints(peer, "endpoints"),
                allowed_ips=tuple(allowed),
                keepalive_s=peer.number(
                    "keepalive_s", 0, MAX_KEEPALIVE_S, default=DEFAULT_KEEPALIVE_S
                ),
                relay=relay,
            )
        )
    _unique(body, "peers", [peer.rig_id for peer in peers])
    attempt_s = (
        body.number("attempt_s", 1, MAX_ATTEMPT_S) if body.has("attempt_s") else None
    )
    connect_timeout_s = (
        body.number("connect_timeout_s", 1, MAX_CONNECT_TIMEOUT_S)
        if body.has("connect_timeout_s")
        else None
    )
    return TunnelUp(
        session_id=session_id,
        address=address,
        listen_port=listen_port,
        peers=tuple(peers),
        attempt_s=attempt_s,
        connect_timeout_s=connect_timeout_s,
    )


def read_worker_start(envelope: protocol.Envelope) -> WorkerStart:
    """The ``worker_start`` in ``envelope``, or :class:`ProtocolError`."""
    body = _start(envelope)
    session_id = body.text("session_id", SESSION_ID)
    cards = []
    for item in body.items("cards", 1, protocol.MAX_CARDS):
        card = body.nested("cards", item)
        cards.append(
            WorkerCard(
                card_index=card.number("card_index", 0, protocol.MAX_CARD_INDEX),
                port=card.number("port", 1, MAX_PORT),
            )
        )
    _unique(body, "cards", [card.card_index for card in cards])
    _unique(body, "cards", [card.port for card in cards])
    return WorkerStart(session_id=session_id, cards=tuple(cards))


def read_head_start(envelope: protocol.Envelope) -> HeadStart:
    """The ``head_start`` in ``envelope``, or :class:`ProtocolError`."""
    body = _start(envelope)
    session_id = body.text("session_id", SESSION_ID)
    model = body.nested("model", body.raw("model"))
    name = model.text("name", MODEL_NAME)
    digest = model.text("digest", DIGEST, optional=True)
    ctx = body.number("ctx", MIN_CTX, MAX_CTX)
    devices: list[LocalDevice | RpcDevice] = []
    for item in body.items("devices", 1, MAX_DEVICES):
        device = body.nested("devices", item)
        kind = device.one_of("kind", ("local", "rpc"))
        if kind == "local":
            devices.append(
                LocalDevice(
                    card_index=device.number("card_index", 0, protocol.MAX_CARD_INDEX)
                )
            )
            continue
        host = _ipv4(device.text("host", IPV4))
        if host is None:
            raise device.refuse("host", "not an address")
        devices.append(RpcDevice(host=host, port=device.number("port", 1, MAX_PORT)))
    shares = []
    for share in body.items("tensor_split", 1, MAX_DEVICES):
        if type(share) is not int or not 0 <= share <= MAX_TENSOR_SHARE:
            raise body.refuse("tensor_split", "a share that is not one")
        shares.append(share)
    if len(shares) != len(devices):
        raise body.refuse("tensor_split", "not one share per device")
    if sum(shares) == 0:
        raise body.refuse("tensor_split", "assigns nothing")
    _unique(
        body,
        "devices",
        [d.card_index for d in devices if isinstance(d, LocalDevice)],
    )
    _unique(
        body,
        "devices",
        [(d.host, d.port) for d in devices if isinstance(d, RpcDevice)],
    )
    if body.has("split_mode"):
        body.one_of("split_mode", ("layer",))
    return HeadStart(
        session_id=session_id,
        model=name,
        digest=digest,
        ctx=ctx,
        devices=tuple(devices),
        tensor_split=tuple(shares),
        n_gpu_layers=body.number(
            "n_gpu_layers", 0, MAX_GPU_LAYERS, default=DEFAULT_GPU_LAYERS
        ),
        slots=_slots(body),
    )


def read_session_query(envelope: protocol.Envelope) -> SessionQuery:
    """The ``session_query`` in ``envelope``, or :class:`ProtocolError`."""
    body = _start(envelope)
    return SessionQuery(session_id=body.text("session_id", SESSION_ID))


def read_session_stop(envelope: protocol.Envelope) -> SessionStop:
    """The ``session_stop`` in ``envelope``, or :class:`ProtocolError`."""
    body = _start(envelope)
    return SessionStop(
        session_id=body.text("session_id", SESSION_ID),
        reason=body.text("reason", protocol.TAG, optional=True),
    )


def read_probe_open(envelope: protocol.Envelope) -> ProbeOpen:
    """The ``probe_open`` in ``envelope``, or :class:`ProtocolError`."""
    body = _start(envelope)
    stun = _endpoints(body, "stun")
    if len(stun) > MAX_STUN_ENDPOINTS:
        raise body.refuse("stun", f"not a list of up to {MAX_STUN_ENDPOINTS}")
    return ProbeOpen(
        probe_id=body.text("probe_id", protocol.MESSAGE_ID),
        token=_token(body, "token"),
        stun=stun,
        ttl_s=body.number(
            "ttl_s", MIN_PROBE_TTL_S, MAX_PROBE_TTL_S, default=DEFAULT_PROBE_TTL_S
        ),
    )


def read_probe_run(envelope: protocol.Envelope) -> ProbeRun:
    """The ``probe_run`` in ``envelope``, or :class:`ProtocolError`."""
    body = _start(envelope)
    peers = []
    for item in body.items("peers", 1, MAX_PEERS):
        peer = body.nested("peers", item)
        endpoints = _endpoints(peer, "endpoints")
        if not endpoints:
            raise peer.refuse("endpoints", f"not a list of 1 to {MAX_ENDPOINTS}")
        peers.append(
            ProbePeer(
                rig_id=peer.text("rig_id", protocol.MESSAGE_ID),
                secret=_token(peer, "secret"),
                endpoints=endpoints,
            )
        )
    _unique(body, "peers", [peer.rig_id for peer in peers])
    _unique(body, "peers", [peer.secret for peer in peers])
    return ProbeRun(
        probe_id=body.text("probe_id", protocol.MESSAGE_ID),
        peers=tuple(peers),
        count=body.number("count", 1, MAX_PROBE_COUNT, default=DEFAULT_PROBE_COUNT),
        interval_ms=body.number(
            "interval_ms",
            MIN_PROBE_INTERVAL_MS,
            MAX_PROBE_INTERVAL_MS,
            default=DEFAULT_PROBE_INTERVAL_MS,
        ),
        bulk_bytes=body.number("bulk_bytes", 0, MAX_PROBE_BULK_BYTES, default=0),
        deadline_ms=body.number(
            "deadline_ms",
            MIN_PROBE_DEADLINE_MS,
            MAX_PROBE_DEADLINE_MS,
            default=DEFAULT_PROBE_DEADLINE_MS,
        ),
    )


def _relayed(body: _Body) -> dict[str, Any]:
    """The fields a relay and a ride share, read one way for both."""
    return {
        "request_id": body.text("request_id", protocol.MESSAGE_ID),
        "endpoint": body.one_of("endpoint", tuple(RELAY_PATHS)),
        "body_bytes": body.number("body_bytes", 0, RELAY_MAX_REQUEST_BYTES),
        "stream": body.flag("stream"),
        "timeout_s": body.number("timeout_s", 1, RELAY_MAX_TIMEOUT_S),
        "max_response_bytes": body.number(
            "max_response_bytes", 1, RELAY_MAX_RESPONSE_BYTES
        ),
        "window": body.number("window", 1, RELAY_MAX_WINDOW),
    }


def read_relay_request(envelope: protocol.Envelope) -> RelayRequest:
    """The ``relay_request`` in ``envelope``, or :class:`ProtocolError`."""
    body = _start(envelope)
    return RelayRequest(
        session_id=body.text("session_id", SESSION_ID), **_relayed(body)
    )


def read_unit_relay_request(envelope: protocol.Envelope) -> UnitRelayRequest:
    """The ``unit_relay_request`` in ``envelope``, or :class:`ProtocolError`."""
    body = _start(envelope)
    return UnitRelayRequest(
        unit_id=body.text("unit_id", protocol.MESSAGE_ID), **_relayed(body)
    )


def read_relay_data(envelope: protocol.Envelope) -> RelayData:
    """The ``relay_data`` in ``envelope``, or :class:`ProtocolError`."""
    body = _start(envelope)
    request_id = body.text("request_id", protocol.MESSAGE_ID)
    seq = body.number("seq", 0, RELAY_MAX_SEQ)
    text = body.raw("data_b64")
    if (
        not isinstance(text, str)
        or not 4 <= len(text) <= RELAY_MAX_CHUNK_B64
        or not BASE64.fullmatch(text)
    ):
        raise body.refuse("data_b64", "not base64 of one chunk")
    try:
        data = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise body.refuse("data_b64", "not base64") from exc
    if len(data) > RELAY_MAX_CHUNK_BYTES:
        raise body.refuse("data_b64", "a chunk over the limit")
    return RelayData(request_id=request_id, seq=seq, data=data)


def read_relay_credit(envelope: protocol.Envelope) -> RelayCredit:
    """The ``relay_credit`` in ``envelope``, or :class:`ProtocolError`."""
    body = _start(envelope)
    return RelayCredit(
        request_id=body.text("request_id", protocol.MESSAGE_ID),
        chunks=body.number("chunks", 1, RELAY_MAX_WINDOW),
    )


def read_relay_cancel(envelope: protocol.Envelope) -> RelayCancel:
    """The ``relay_cancel`` in ``envelope``, or :class:`ProtocolError`."""
    body = _start(envelope)
    return RelayCancel(
        request_id=body.text("request_id", protocol.MESSAGE_ID),
        reason=body.text("reason", protocol.TAG, optional=True),
    )


# --- what the agent sends ---------------------------------------------------------


def _need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def _frame(kind: str, body: dict[str, Any], re: str | None) -> str:
    message: dict[str, Any] = {
        "v": protocol.PROTOCOL_VERSION,
        "type": kind,
        "id": protocol.new_id(),
        "body": body,
    }
    if re is not None:
        _need(bool(protocol.MESSAGE_ID.fullmatch(re)), "re: not a message id")
        message["re"] = re
    text = json.dumps(message, separators=(",", ":"))
    _need(len(text.encode("utf-8")) <= protocol.MAX_MESSAGE_BYTES, "message too large")
    return text


def endpoint_body(endpoint: Endpoint) -> dict[str, Any]:
    """An endpoint as the wire carries it; ``ValueError`` if it is not one."""
    _need(bool(HOST.fullmatch(endpoint.host)), "endpoints: a host not of its shape")
    _need(1 <= endpoint.port <= MAX_PORT, "endpoints: a port that is not one")
    _need(bool(protocol.TAG.fullmatch(endpoint.kind)), "endpoints: a kind not a tag")
    return {"host": endpoint.host, "port": endpoint.port, "kind": endpoint.kind}


def _rtt(value: int | None, field: str) -> None:
    _need(value is None or 0 <= value <= MAX_RTT_US, f"{field}: out of bounds")


def session_prepared(
    re: str,
    *,
    session_id: str,
    public_key: str,
    listen_port: int,
    endpoints: Sequence[Endpoint],
    stun_rtt_us: int | None = None,
) -> str:
    """The ``session_prepared`` answering ``re``."""
    _need(bool(SESSION_ID.fullmatch(session_id)), "session_id: not a session id")
    _need(bool(WIREGUARD_KEY.fullmatch(public_key)), "public_key: not a key")
    _need(1 <= listen_port <= MAX_PORT, "listen_port: not a port")
    _need(len(endpoints) <= MAX_ENDPOINTS, f"endpoints: more than {MAX_ENDPOINTS}")
    _rtt(stun_rtt_us, "stun_rtt_us")
    body: dict[str, Any] = {
        "session_id": session_id,
        "public_key": public_key,
        "listen_port": listen_port,
        "endpoints": [endpoint_body(e) for e in endpoints],
    }
    if stun_rtt_us is not None:
        body["stun_rtt_us"] = stun_rtt_us
    return _frame("session_prepared", body, re)


@dataclass(frozen=True, kw_only=True)
class PeerPath:
    """How this rig reaches one peer: ``path`` is ``lan``, ``ipv6``,
    ``direct``, ``relay`` or ``none``."""

    rig_id: str
    path: str
    endpoint: Endpoint | None = None
    rtt_us: int | None = None


def tunnel_report(re: str | None, *, session_id: str, peers: Sequence[PeerPath]) -> str:
    """The ``tunnel_report`` answering ``tunnel_up`` ``re``, or unprompted."""
    _need(bool(SESSION_ID.fullmatch(session_id)), "session_id: not a session id")
    _need(1 <= len(peers) <= MAX_PEERS, f"peers: not 1 to {MAX_PEERS}")
    _need(len({p.rig_id for p in peers}) == len(peers), "peers: a rig twice")
    paths = []
    for peer in peers:
        _need(bool(protocol.MESSAGE_ID.fullmatch(peer.rig_id)), "rig_id: not an id")
        _need(bool(protocol.TAG.fullmatch(peer.path)), "path: not a tag")
        _rtt(peer.rtt_us, "rtt_us")
        entry: dict[str, Any] = {"rig_id": peer.rig_id, "path": peer.path}
        if peer.endpoint is not None:
            entry["endpoint"] = endpoint_body(peer.endpoint)
        if peer.rtt_us is not None:
            entry["rtt_us"] = peer.rtt_us
        paths.append(entry)
    return _frame("tunnel_report", {"session_id": session_id, "peers": paths}, re)


def probe_opened(
    re: str,
    *,
    probe_id: str,
    endpoints: Sequence[Endpoint],
    stun_rtt_us: int | None,
) -> str:
    """The ``probe_opened`` answering ``probe_open`` ``re``."""
    _need(bool(protocol.MESSAGE_ID.fullmatch(probe_id)), "probe_id: not an id")
    _need(len(endpoints) <= MAX_ENDPOINTS, f"endpoints: more than {MAX_ENDPOINTS}")
    _rtt(stun_rtt_us, "stun_rtt_us")
    body: dict[str, Any] = {
        "probe_id": probe_id,
        "endpoints": [endpoint_body(e) for e in endpoints],
    }
    if stun_rtt_us is not None:
        body["stun_rtt_us"] = stun_rtt_us
    return _frame("probe_opened", body, re)


@dataclass(frozen=True, kw_only=True)
class ProbeOutcome:
    """What a probe found of one peer."""

    rig_id: str
    reached: bool
    endpoint: Endpoint | None = None
    rtt_us: int | None = None
    rtt_min_us: int | None = None
    loss_pct: int | None = None
    rate_kbps: int | None = None


def probe_result(re: str, *, probe_id: str, results: Sequence[ProbeOutcome]) -> str:
    """The ``probe_result`` answering ``probe_run`` ``re``."""
    _need(bool(protocol.MESSAGE_ID.fullmatch(probe_id)), "probe_id: not an id")
    _need(len(results) <= MAX_PEERS, f"results: more than {MAX_PEERS}")
    _need(len({r.rig_id for r in results}) == len(results), "results: a rig twice")
    found = []
    for result in results:
        _need(bool(protocol.MESSAGE_ID.fullmatch(result.rig_id)), "rig_id: not an id")
        _rtt(result.rtt_us, "rtt_us")
        _rtt(result.rtt_min_us, "rtt_min_us")
        _need(
            result.loss_pct is None or 0 <= result.loss_pct <= MAX_PCT,
            "loss_pct: not 0 to 100",
        )
        _need(
            result.rate_kbps is None or 1 <= result.rate_kbps <= MAX_RATE_KBPS,
            "rate_kbps: out of bounds",
        )
        entry: dict[str, Any] = {"rig_id": result.rig_id, "reached": result.reached}
        if result.endpoint is not None:
            entry["endpoint"] = endpoint_body(result.endpoint)
        for name in ("rtt_us", "rtt_min_us", "loss_pct", "rate_kbps"):
            value = getattr(result, name)
            if value is not None:
                entry[name] = value
        found.append(entry)
    return _frame("probe_result", {"probe_id": probe_id, "results": found}, re)


def scrub(text: str) -> str:
    """``text`` with control characters and bidirectional overrides replaced,
    newlines and tabs kept, cut to the longest log excerpt."""
    kept = "".join(
        char
        if char in "\n\t" or protocol.CARD_NAME.fullmatch(char)
        else "\N{REPLACEMENT CHARACTER}"
        for char in text
    )
    return kept[-LOG_EXCERPT_MAX_CHARS:]


def session_status(
    re: str | None,
    *,
    session_id: str,
    state: str,
    role: str | None = None,
    error_code: str | None = None,
    progress_pct: int | None = None,
    log_excerpt: str = "",
) -> str:
    """A ``session_status``, answering ``re`` or unprompted."""
    _need(bool(SESSION_ID.fullmatch(session_id)), "session_id: not a session id")
    _need(state in STATES, "state: not a session state")
    body: dict[str, Any] = {"session_id": session_id, "state": state}
    if role is not None:
        _need(role in ROLES, "role: not a role")
        body["role"] = role
    if error_code is not None:
        _need(bool(protocol.TAG.fullmatch(error_code)), "error_code: not a code")
        body["error_code"] = error_code
    if progress_pct is not None:
        _need(0 <= progress_pct <= 100, "progress_pct: not 0 to 100")
        body["progress_pct"] = progress_pct
    if log_excerpt:
        body["log_excerpt"] = scrub(log_excerpt)
    return _frame("session_status", body, re)


def relay_response(request_id: str, *, status: int, content_type: str) -> str:
    """The ``relay_response`` that opens a relayed answer."""
    _need(bool(protocol.MESSAGE_ID.fullmatch(request_id)), "request_id: not an id")
    _need(100 <= status <= 599, "status: not an HTTP status")
    _need(
        len(content_type) <= MAX_CONTENT_TYPE
        and bool(CONTENT_TYPE.fullmatch(content_type)),
        "content_type: not of its shape",
    )
    return _frame(
        "relay_response",
        {"request_id": request_id, "status": status, "content_type": content_type},
        None,
    )


def relay_data(request_id: str, *, seq: int, data: bytes) -> str:
    """One ``relay_data`` frame of the relayed answer."""
    _need(bool(protocol.MESSAGE_ID.fullmatch(request_id)), "request_id: not an id")
    _need(0 <= seq <= RELAY_MAX_SEQ, "seq: out of bounds")
    _need(0 < len(data) <= RELAY_MAX_CHUNK_BYTES, "data: not one chunk")
    return _frame(
        "relay_data",
        {
            "request_id": request_id,
            "seq": seq,
            "data_b64": base64.b64encode(data).decode("ascii"),
        },
        None,
    )


def relay_end(request_id: str, *, outcome: str, error_code: str | None = None) -> str:
    """The one ``relay_end`` of a relayed request."""
    _need(bool(protocol.MESSAGE_ID.fullmatch(request_id)), "request_id: not an id")
    _need(outcome in RELAY_OUTCOMES, "outcome: not a relay outcome")
    body: dict[str, Any] = {"request_id": request_id, "outcome": outcome}
    if error_code is not None:
        _need(bool(protocol.TAG.fullmatch(error_code)), "error_code: not a code")
        body["error_code"] = error_code
    return _frame("relay_end", body, None)


def peer_rtt(samples: Sequence[tuple[str, int]]) -> str:
    """A ``peer_rtt`` of ``(rig_id, rtt_us)`` samples."""
    _need(1 <= len(samples) <= MAX_RTT_SAMPLES, "samples: not 1 to 32")
    body = []
    for rig_id, rtt_us in samples:
        _need(bool(protocol.MESSAGE_ID.fullmatch(rig_id)), "rig_id: not an id")
        _need(0 <= rtt_us <= MAX_RTT_US, "rtt_us: out of bounds")
        body.append({"rig_id": rig_id, "rtt_us": rtt_us})
    return _frame("peer_rtt", {"samples": body}, None)


@dataclass(frozen=True, kw_only=True)
class AdvertisedUnit:
    """One unit a host shares with riders, as its advert says it.

    ``slots`` is how many requests the unit serves at once and ``ctx`` the
    context of each; ``free_slots`` the slots the host's own requests leave
    free now (the rides it serves are not taken off); ``rider_cap`` the most
    rides at once the host allows, below ``slots``, so rides alone never fill
    a unit. The host's own requests go first, and a free slot is enough: a
    unit takes a ride while one of its slots is free and fewer than
    ``rider_cap`` rides run on it; no slot is kept free for the host beyond
    that.
    """

    unit_id: str
    model: str
    slots: int
    ctx: int
    free_slots: int
    rider_cap: int


def _whole(value: object, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def unit_advert(units: Sequence[AdvertisedUnit]) -> str:
    """The ``unit_advert`` of every unit the host shares, the whole set: an
    empty one withdraws them all. ``ValueError`` for one the schema refuses."""
    _need(len(units) <= MAX_UNITS, f"units: more than {MAX_UNITS}")
    _need(len({unit.unit_id for unit in units}) == len(units), "units: an id twice")
    _need(len({unit.model for unit in units}) == len(units), "units: a model twice")
    body = []
    for unit in units:
        _need(
            isinstance(unit.unit_id, str)
            and bool(protocol.MESSAGE_ID.fullmatch(unit.unit_id)),
            "unit_id: not an id",
        )
        _need(
            isinstance(unit.model, str) and bool(MODEL_NAME.fullmatch(unit.model)),
            "model: not of its shape",
        )
        _need(_whole(unit.slots, 1, MAX_SLOTS), f"slots: not 1 to {MAX_SLOTS}")
        _need(_whole(unit.ctx, MIN_CTX, MAX_CTX), "ctx: out of bounds")
        _need(_whole(unit.free_slots, 0, unit.slots), "free_slots: not 0 to slots")
        _need(
            _whole(unit.rider_cap, 1, unit.slots - 1),
            "rider_cap: not 1 to one below slots",
        )
        body.append(
            {
                "unit_id": unit.unit_id,
                "model": unit.model,
                "slots": unit.slots,
                "ctx": unit.ctx,
                "free_slots": unit.free_slots,
                "rider_cap": unit.rider_cap,
            }
        )
    return _frame("unit_advert", {"units": body}, None)


def ack(re: str) -> str:
    """The ``ack`` of a command done, or accepted: ``re`` is the command's id."""
    return _frame("ack", {}, re)


def refusal(re: str, code: str, message: str) -> str:
    """The ``error`` refusing command ``re`` with ``code``."""
    return protocol.error(protocol.new_id(), code=code, message=message, re=re)
