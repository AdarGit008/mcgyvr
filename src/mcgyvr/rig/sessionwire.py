"""The session and relay messages of the hub's protocol v1, as the agent speaks them.

The hub's schema is the one definition (``tests/rig_schema.py`` pins it);
this module reads the commands the hub sends a rig that offered to lend
(``session_prepare``, ``tunnel_up``, ``worker_start``, ``head_start``,
``session_query``, ``session_stop``, ``relay_request``, ``relay_data``,
``relay_credit``, ``relay_cancel``) and writes the agent's side
(``session_prepared``, ``session_status``, ``relay_response``,
``relay_data``, ``relay_end``, ``peer_rtt``).

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


# --- what the hub sends ----------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Endpoint:
    """A candidate address a tunnel is reached at."""

    host: str
    port: int
    kind: str


@dataclass(frozen=True, kw_only=True)
class SessionPrepare:
    session_id: str
    role: Role


@dataclass(frozen=True, kw_only=True)
class TunnelPeer:
    rig_id: str
    public_key: str
    endpoints: tuple[Endpoint, ...]
    allowed_ips: tuple[ipaddress.IPv4Network, ...]
    keepalive_s: int


@dataclass(frozen=True, kw_only=True)
class TunnelUp:
    session_id: str
    address: ipaddress.IPv4Interface
    listen_port: int
    peers: tuple[TunnelPeer, ...]


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
    ctx: int
    devices: tuple[LocalDevice | RpcDevice, ...]
    tensor_split: tuple[int, ...]
    n_gpu_layers: int


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


def _start(envelope: protocol.Envelope) -> _Body:
    return _Body(envelope.body, "body", envelope.id)


def read_session_prepare(envelope: protocol.Envelope) -> SessionPrepare:
    """The ``session_prepare`` in ``envelope``, or :class:`ProtocolError`."""
    body = _start(envelope)
    role = body.one_of("role", ROLES)
    return SessionPrepare(
        session_id=body.text("session_id", SESSION_ID),
        role="head" if role == "head" else "worker",
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
        peers.append(
            TunnelPeer(
                rig_id=peer.text("rig_id", protocol.MESSAGE_ID),
                public_key=peer.text("public_key", WIREGUARD_KEY),
                endpoints=_endpoints(peer, "endpoints"),
                allowed_ips=tuple(allowed),
                keepalive_s=peer.number(
                    "keepalive_s", 0, MAX_KEEPALIVE_S, default=DEFAULT_KEEPALIVE_S
                ),
            )
        )
    _unique(body, "peers", [peer.rig_id for peer in peers])
    return TunnelUp(
        session_id=session_id,
        address=address,
        listen_port=listen_port,
        peers=tuple(peers),
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


def read_relay_request(envelope: protocol.Envelope) -> RelayRequest:
    """The ``relay_request`` in ``envelope``, or :class:`ProtocolError`."""
    body = _start(envelope)
    return RelayRequest(
        session_id=body.text("session_id", SESSION_ID),
        request_id=body.text("request_id", protocol.MESSAGE_ID),
        endpoint=body.one_of("endpoint", tuple(RELAY_PATHS)),
        body_bytes=body.number("body_bytes", 0, RELAY_MAX_REQUEST_BYTES),
        stream=body.flag("stream"),
        timeout_s=body.number("timeout_s", 1, RELAY_MAX_TIMEOUT_S),
        max_response_bytes=body.number(
            "max_response_bytes", 1, RELAY_MAX_RESPONSE_BYTES
        ),
        window=body.number("window", 1, RELAY_MAX_WINDOW),
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


def session_prepared(
    re: str,
    *,
    session_id: str,
    public_key: str,
    listen_port: int,
    endpoints: Sequence[Endpoint],
) -> str:
    """The ``session_prepared`` answering ``re``."""
    _need(bool(SESSION_ID.fullmatch(session_id)), "session_id: not a session id")
    _need(bool(WIREGUARD_KEY.fullmatch(public_key)), "public_key: not a key")
    _need(1 <= listen_port <= MAX_PORT, "listen_port: not a port")
    _need(len(endpoints) <= MAX_ENDPOINTS, f"endpoints: more than {MAX_ENDPOINTS}")
    return _frame(
        "session_prepared",
        {
            "session_id": session_id,
            "public_key": public_key,
            "listen_port": listen_port,
            "endpoints": [endpoint_body(e) for e in endpoints],
        },
        re,
    )


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


def ack(re: str) -> str:
    """The ``ack`` of a command done, or accepted: ``re`` is the command's id."""
    return _frame("ack", {}, re)


def refusal(re: str, code: str, message: str) -> str:
    """The ``error`` refusing command ``re`` with ``code``."""
    return protocol.error(protocol.new_id(), code=code, message=message, re=re)
