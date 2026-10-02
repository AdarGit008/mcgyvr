"""The hub's agent protocol, version 1, as the rig agent speaks it.

The hub publishes the protocol as a JSON Schema, written from its own message
models; that schema is the one definition of the wire. This module states the
limits the agent needs from it and nothing else, and the tests hold every one
of them, and every frame written here, to a pinned copy of the hub's file
(``tests/rig_schema.py`` says how the copy is pinned and moved).

Every message is one JSON object in one websocket frame::

    {"v": 1, "type": "<type>", "id": "<sender-chosen id>", "re": "<id>", "body": {}}

``re`` names the message being answered. The agent sends ``hello`` first (its
identity and hardware), then ``heartbeat``; the hub answers each with ``ack``,
and refuses with ``error`` (a fatal one followed by a close with a
:class:`CloseCode`). Later versions of the hub add commands, so a frame is read
in two steps: :func:`decode` takes any well formed envelope, whatever its
type, and :func:`read_ack` and :func:`read_error` read the bodies of the types
the agent knows. Unknown fields are ignored and an error code the agent does
not know is still an error, as the protocol asks of a receiver.

What the hub sends is untrusted. Nothing here evaluates it beyond these
checks, and a refusal names the field, never the value the hub sent.
"""

from __future__ import annotations

import enum
import json
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

#: The version the agent speaks; the hub refuses any other.
PROTOCOL_VERSION = 1
#: The largest frame either side sends, in bytes of UTF-8.
MAX_MESSAGE_BYTES = 64 * 1024
#: The most frames a side sends a second; the hub closes a channel that sends
#: more.
MAX_FRAMES_PER_SECOND = 100
#: The most cards one report carries.
MAX_CARDS = 16
#: The highest card index a report may carry.
MAX_CARD_INDEX = 63
#: The longest card name a report may carry, in characters.
CARD_NAME_MAX = 128
#: The bound on every size in MiB: a sanity bound, not a limit.
MAX_MB = 1 << 30
#: The longest error text, in characters.
MAX_ERROR_TEXT = 500
#: The heartbeat interval a hub may ask for, in seconds, low and high.
HEARTBEAT_INTERVAL_S = (1, 3600)
#: The most models a hello names.
MAX_MODELS = 64
#: The most sessions a hello says the agent is running.
MAX_SESSIONS_REPORTED = 4
#: The largest model file a hello names, in bytes.
MAX_MODEL_BYTES = 1 << 50
#: The most layers, the longest trained context, and the largest of a model's
#: other counts a hello carries.
MAX_LAYERS = 4096
MAX_COUNT = 1 << 20
#: The largest KV cache size per token of context a hello carries, in bytes.
MAX_KV_BYTES_PER_TOKEN = 1 << 30

#: The shapes of the wire's strings, matched whole.
MESSAGE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
TAG = re.compile(r"[a-z][a-z0-9_]{0,63}")
MACHINE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
AGENT_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}")
#: Printable text: no control character and no bidirectional override. The
#: hub's schema writes the excluded characters themselves, not escapes, so the
#: pattern is built of them too and its text is the schema's.
CARD_NAME = re.compile("[^\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]+")


class CloseCode(enum.IntEnum):
    """The websocket close codes the hub ends a channel with."""

    POLICY = 1008  # refused: bad token, bad hello, machine mismatch, flooding
    REVOKED = 4001  # the rig was deleted or its token rotated
    TIMEOUT = 4008  # no hello or heartbeat in time
    SUPERSEDED = 4009  # a newer connection for the same rig took over


class ErrorCode(enum.StrEnum):
    """The error codes the protocol names today. The set is open: a code not
    listed here is still an error, read as one."""

    BAD_MESSAGE = "bad_message"
    UNSUPPORTED_VERSION = "unsupported_version"
    UNSUPPORTED_TYPE = "unsupported_type"
    EXPECTED_HELLO = "expected_hello"
    MACHINE_MISMATCH = "machine_mismatch"
    REVOKED = "revoked"
    TIMEOUT = "timeout"
    SUPERSEDED = "superseded"
    RATE_LIMITED = "rate_limited"


class ProtocolError(Exception):
    """A frame the agent does not accept; ``re`` is its id when that was read."""

    def __init__(self, code: str, message: str, re: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message[:MAX_ERROR_TEXT]
        self.re = re


@dataclass(frozen=True, kw_only=True)
class Envelope:
    """One well formed frame, of any type; ``body`` is not yet read."""

    type: str
    id: str
    re: str | None
    body: Mapping[str, Any]


@dataclass(frozen=True, kw_only=True)
class Ack:
    """The hub's ``ack``: ``rig_id`` and ``heartbeat_interval_s`` answer a hello."""

    re: str
    rig_id: str | None
    heartbeat_interval_s: int | None


@dataclass(frozen=True, kw_only=True)
class Error:
    """The hub's ``error``. ``code`` may be one :class:`ErrorCode` does not list."""

    re: str | None
    code: str
    message: str


@dataclass(frozen=True, kw_only=True)
class CardReport:
    """One card as a hello reports it; sizes in MiB."""

    index: int
    name: str
    vram_total_mb: int
    vram_free_mb: int


@dataclass(frozen=True, kw_only=True)
class ModelInfo:
    """A model file on the rig's disk, named for the hub, with what planning
    needs from its header; a count not read is ``None``."""

    name: str
    size_bytes: int
    digest: str | None = None
    arch: str | None = None
    n_layers: int | None = None
    n_ctx_train: int | None = None
    n_embd: int | None = None
    n_head: int | None = None
    n_head_kv: int | None = None
    kv_bytes_per_token: int | None = None


@dataclass(frozen=True, kw_only=True)
class Offer:
    """What a hello says this rig lends: its roles, the runtime it runs them
    in, the endpoints its tunnel is reached at, the models it can serve, and
    the sessions it is running now. A rig that lends nothing says none of it."""

    roles: tuple[str, ...]
    runtime: str | None
    endpoints: tuple[tuple[str, int, str], ...]  # host, port, kind
    models: tuple[ModelInfo, ...]
    sessions: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class CardReading:
    """One card's free memory as a heartbeat reports it, in MiB."""

    index: int
    vram_free_mb: int


def new_id() -> str:
    """A message id of the shape the protocol takes."""
    return uuid.uuid4().hex


def _is_int(value: object) -> bool:
    return type(value) is int


def _refuse_constant(name: str) -> Any:
    raise ValueError(f"{name} is not JSON")


def decode(raw: str | bytes) -> Envelope:
    """One hub frame as an envelope, or :class:`ProtocolError`.

    A frame over :data:`MAX_MESSAGE_BYTES`, not UTF-8, not JSON, or not one
    object is ``bad_message``; a version other than :data:`PROTOCOL_VERSION`
    is ``unsupported_version``; a malformed ``type``, ``id``, ``re`` or
    ``body`` is ``bad_message``, carrying the frame's id when that was read.
    """
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError(ErrorCode.BAD_MESSAGE, "message too large")
    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if len(text.encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise ProtocolError(ErrorCode.BAD_MESSAGE, "message too large")
        data: Any = json.loads(text, parse_constant=_refuse_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ProtocolError(ErrorCode.BAD_MESSAGE, "not valid UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise ProtocolError(ErrorCode.BAD_MESSAGE, "message must be a JSON object")
    msg_id = data.get("id")
    said = msg_id if isinstance(msg_id, str) and MESSAGE_ID.fullmatch(msg_id) else None
    version = data.get("v")
    if not _is_int(version) or version != PROTOCOL_VERSION:
        raise ProtocolError(
            ErrorCode.UNSUPPORTED_VERSION,
            f"this agent speaks protocol v{PROTOCOL_VERSION}",
            said,
        )
    kind = data.get("type")
    if not isinstance(kind, str) or not TAG.fullmatch(kind):
        raise ProtocolError(ErrorCode.BAD_MESSAGE, "type: not a type tag", said)
    if said is None:
        raise ProtocolError(ErrorCode.BAD_MESSAGE, "id: not a message id")
    answered = data.get("re")
    if answered is not None and not (
        isinstance(answered, str) and MESSAGE_ID.fullmatch(answered)
    ):
        raise ProtocolError(ErrorCode.BAD_MESSAGE, "re: not a message id", said)
    body = data.get("body", {})
    if not isinstance(body, dict):
        raise ProtocolError(ErrorCode.BAD_MESSAGE, "body: not an object", said)
    return Envelope(type=kind, id=said, re=answered, body=body)


def read_ack(envelope: Envelope) -> Ack:
    """The ``ack`` in ``envelope``, or :class:`ProtocolError`."""
    if envelope.re is None:
        raise ProtocolError(
            ErrorCode.BAD_MESSAGE, "re: an ack answers a message", envelope.id
        )
    rig_id = envelope.body.get("rig_id")
    if rig_id is not None and not isinstance(rig_id, str):
        raise ProtocolError(
            ErrorCode.BAD_MESSAGE, "body.rig_id: not a string", envelope.id
        )
    interval = envelope.body.get("heartbeat_interval_s")
    low, high = HEARTBEAT_INTERVAL_S
    if interval is not None and not (_is_int(interval) and low <= interval <= high):
        raise ProtocolError(
            ErrorCode.BAD_MESSAGE,
            f"body.heartbeat_interval_s: not a whole number of {low} to {high}",
            envelope.id,
        )
    return Ack(re=envelope.re, rig_id=rig_id, heartbeat_interval_s=interval)


def read_error(envelope: Envelope) -> Error:
    """The ``error`` in ``envelope``, or :class:`ProtocolError`."""
    code = envelope.body.get("code")
    if not isinstance(code, str) or not TAG.fullmatch(code):
        raise ProtocolError(
            ErrorCode.BAD_MESSAGE, "body.code: not an error code", envelope.id
        )
    message = envelope.body.get("message", "")
    if not isinstance(message, str) or len(message) > MAX_ERROR_TEXT:
        raise ProtocolError(
            ErrorCode.BAD_MESSAGE,
            f"body.message: not a text of at most {MAX_ERROR_TEXT} characters",
            envelope.id,
        )
    return Error(re=envelope.re, code=code, message=message)


# --- writing -----------------------------------------------------------------


def _need(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError(why)


def _megabytes(value: object, field: str) -> None:
    _need(_is_int(value), f"{field}: not a whole number")
    assert isinstance(value, int)
    _need(0 <= value <= MAX_MB, f"{field}: not 0 to {MAX_MB} MiB")


def _cards(cards: Sequence[CardReport] | Sequence[CardReading]) -> None:
    _need(len(cards) <= MAX_CARDS, f"cards: more than {MAX_CARDS}")
    indexes = [card.index for card in cards]
    for index in indexes:
        _need(
            _is_int(index) and 0 <= index <= MAX_CARD_INDEX,
            f"cards: index not 0 to {MAX_CARD_INDEX}",
        )
    _need(len(set(indexes)) == len(indexes), "cards: an index twice")


def _frame(kind: str, message_id: str, body: dict[str, Any], re: str | None) -> str:
    _need(bool(MESSAGE_ID.fullmatch(message_id)), "id: not a message id")
    _need(re is None or bool(MESSAGE_ID.fullmatch(re)), "re: not a message id")
    message: dict[str, Any] = {
        "v": PROTOCOL_VERSION,
        "type": kind,
        "id": message_id,
        "body": body,
    }
    if re is not None:
        message["re"] = re
    text = json.dumps(message, separators=(",", ":"))
    _need(len(text.encode("utf-8")) <= MAX_MESSAGE_BYTES, "message too large")
    return text


def _bounded(value: int | None, low: int, high: int, field: str) -> None:
    _need(
        value is None or (_is_int(value) and low <= value <= high),
        f"{field}: not a whole number of {low} to {high}",
    )


#: The shapes of a model's name, digest and architecture, and of a runtime.
MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+=@-]{0,127}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
SHORT_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}")
RUNTIME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,199}")
ENDPOINT_HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9.:-]{0,252}")
#: The roles a rig may offer.
ROLES = ("head", "worker")
#: The most endpoints a hello names.
MAX_ENDPOINTS = 8


def _model_body(model: ModelInfo) -> dict[str, Any]:
    _need(bool(MODEL_NAME.fullmatch(model.name)), "models: a name not of its shape")
    _bounded(model.size_bytes, 1, MAX_MODEL_BYTES, "models.size_bytes")
    _need(
        model.digest is None or bool(DIGEST.fullmatch(model.digest)),
        "models.digest: not a sha256 digest",
    )
    _need(
        model.arch is None or bool(SHORT_TAG.fullmatch(model.arch)),
        "models.arch: not of its shape",
    )
    _bounded(model.n_layers, 1, MAX_LAYERS, "models.n_layers")
    _bounded(model.n_ctx_train, 1, MAX_COUNT, "models.n_ctx_train")
    for field in ("n_embd", "n_head", "n_head_kv"):
        _bounded(getattr(model, field), 1, MAX_COUNT, f"models.{field}")
    _bounded(
        model.kv_bytes_per_token, 1, MAX_KV_BYTES_PER_TOKEN, "models.kv_bytes_per_token"
    )
    body: dict[str, Any] = {"name": model.name, "size_bytes": model.size_bytes}
    for field in (
        "digest",
        "arch",
        "n_layers",
        "n_ctx_train",
        "n_embd",
        "n_head",
        "n_head_kv",
        "kv_bytes_per_token",
    ):
        value = getattr(model, field)
        if value is not None:
            body[field] = value
    return body


def _offer_body(offer: Offer) -> dict[str, Any]:
    _need(len(offer.roles) <= len(ROLES), "capabilities.roles: too many")
    _need(
        all(role in ROLES for role in offer.roles)
        and len(set(offer.roles)) == len(offer.roles),
        "capabilities.roles: not distinct roles",
    )
    _need(
        offer.runtime is None or bool(RUNTIME.fullmatch(offer.runtime)),
        "capabilities.runtime: not of its shape",
    )
    _need(len(offer.endpoints) <= MAX_ENDPOINTS, "endpoints: too many")
    for host, port, kind in offer.endpoints:
        _need(bool(ENDPOINT_HOST.fullmatch(host)), "endpoints: a host not of its shape")
        _need(_is_int(port) and 1 <= port <= 65535, "endpoints: a port that is not one")
        _need(bool(TAG.fullmatch(kind)), "endpoints: a kind that is not a tag")
    _need(len(offer.models) <= MAX_MODELS, f"models: more than {MAX_MODELS}")
    names = [model.name for model in offer.models]
    _need(len(set(names)) == len(names), "models: a name twice")
    _need(
        len(offer.sessions) <= MAX_SESSIONS_REPORTED,
        f"sessions: more than {MAX_SESSIONS_REPORTED}",
    )
    _need(
        all(MESSAGE_ID.fullmatch(session) for session in offer.sessions),
        "sessions: not session ids",
    )
    capabilities: dict[str, Any] = {"roles": list(offer.roles)}
    if offer.runtime is not None:
        capabilities["runtime"] = offer.runtime
    return {
        "capabilities": capabilities,
        "endpoints": [
            {"host": host, "port": port, "kind": kind}
            for host, port, kind in offer.endpoints
        ],
        "models": [_model_body(model) for model in offer.models],
        "sessions": list(offer.sessions),
    }


def hello(
    message_id: str,
    *,
    machine_id: str,
    agent_version: str,
    ram_total_mb: int,
    ram_free_mb: int | None,
    cards: Sequence[CardReport],
    offer: Offer | None = None,
) -> str:
    """The ``hello`` frame, or ``ValueError`` naming what the schema refuses.

    ``offer`` is what the rig lends; a hello without one says nothing of
    sessions, and the hub sends such a rig no session command."""
    _need(bool(MACHINE_ID.fullmatch(machine_id)), "machine_id: not a machine id")
    _need(bool(AGENT_VERSION.fullmatch(agent_version)), "agent_version: not a version")
    _megabytes(ram_total_mb, "ram_total_mb")
    if ram_free_mb is not None:
        _megabytes(ram_free_mb, "ram_free_mb")
    _cards(cards)
    for card in cards:
        _need(
            isinstance(card.name, str)
            and len(card.name) <= CARD_NAME_MAX
            and bool(CARD_NAME.fullmatch(card.name)),
            f"cards: a name not 1 to {CARD_NAME_MAX} printable characters",
        )
        _megabytes(card.vram_total_mb, "cards.vram_total_mb")
        _megabytes(card.vram_free_mb, "cards.vram_free_mb")
        _need(
            card.vram_free_mb <= card.vram_total_mb,
            "cards: vram_free_mb exceeds vram_total_mb",
        )
    body: dict[str, Any] = {
        "machine_id": machine_id,
        "agent_version": agent_version,
        "ram_total_mb": ram_total_mb,
        "cards": [
            {
                "index": card.index,
                "name": card.name,
                "vram_total_mb": card.vram_total_mb,
                "vram_free_mb": card.vram_free_mb,
            }
            for card in cards
        ],
    }
    if ram_free_mb is not None:
        body["ram_free_mb"] = ram_free_mb
    if offer is not None:
        body.update(_offer_body(offer))
    return _frame("hello", message_id, body, None)


def heartbeat(
    message_id: str, *, ram_free_mb: int | None, cards: Sequence[CardReading]
) -> str:
    """The ``heartbeat`` frame, or ``ValueError`` naming what the schema refuses."""
    if ram_free_mb is not None:
        _megabytes(ram_free_mb, "ram_free_mb")
    _cards(cards)
    for card in cards:
        _megabytes(card.vram_free_mb, "cards.vram_free_mb")
    body: dict[str, Any] = {
        "cards": [
            {"index": card.index, "vram_free_mb": card.vram_free_mb} for card in cards
        ]
    }
    if ram_free_mb is not None:
        body["ram_free_mb"] = ram_free_mb
    return _frame("heartbeat", message_id, body, None)


def error(message_id: str, *, code: str, message: str, re: str | None) -> str:
    """An ``error`` frame answering ``re``; ``message`` is cut to fit."""
    _need(bool(TAG.fullmatch(code)), "code: not an error code")
    return _frame(
        "error", message_id, {"code": code, "message": message[:MAX_ERROR_TEXT]}, re
    )
