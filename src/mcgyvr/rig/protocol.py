""

from __future__ import annotations

import enum
import json
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

#
PROTOCOL_VERSION = 1
#
MAX_MESSAGE_BYTES = 64 * 1024
#
#
MAX_FRAMES_PER_SECOND = 100
#
MAX_CARDS = 16
#
MAX_CARD_INDEX = 63
#
CARD_NAME_MAX = 128
#
MAX_MB = 1 << 30
#
MAX_ERROR_TEXT = 500
#
HEARTBEAT_INTERVAL_S = (1, 3600)
#
MAX_MODELS = 64
#
MAX_SESSIONS_REPORTED = 4
#
MAX_MODEL_BYTES = 1 << 50
#
#
MAX_LAYERS = 4096
MAX_COUNT = 1 << 20
#
MAX_KV_BYTES_PER_TOKEN = 1 << 30

#
MESSAGE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
TAG = re.compile(r"[a-z][a-z0-9_]{0,63}")
MACHINE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
AGENT_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}")
#
#
#
CARD_NAME = re.compile("[^\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]+")


class CloseCode(enum.IntEnum):
    ""

    POLICY = 1008  #
    REVOKED = 4001  #
    TIMEOUT = 4008  #
    SUPERSEDED = 4009  #


class ErrorCode(enum.StrEnum):
    ""

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
    ""

    def __init__(self, code: str, message: str, re: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message[:MAX_ERROR_TEXT]
        self.re = re


@dataclass(frozen=True, kw_only=True)
class Envelope:
    ""

    type: str
    id: str
    re: str | None
    body: Mapping[str, Any]


@dataclass(frozen=True, kw_only=True)
class Ack:
    ""

    re: str
    rig_id: str | None
    heartbeat_interval_s: int | None


@dataclass(frozen=True, kw_only=True)
class Error:
    ""

    re: str | None
    code: str
    message: str


@dataclass(frozen=True, kw_only=True)
class CardReport:
    ""

    index: int
    name: str
    vram_total_mb: int
    vram_free_mb: int


@dataclass(frozen=True, kw_only=True)
class ModelInfo:
    ""

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
    #
    #
    #
    embd_bytes: int | None = None
    output_bytes: int | None = None


@dataclass(frozen=True, kw_only=True)
class Offer:
    ""

    roles: tuple[str, ...]
    runtime: str | None
    endpoints: tuple[tuple[str, int, str], ...]  #
    models: tuple[ModelInfo, ...]
    sessions: tuple[str, ...]
    features: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class CardReading:
    ""

    index: int
    vram_free_mb: int


def new_id() -> str:
    ""
    return uuid.uuid4().hex


def _is_int(value: object) -> bool:
    return type(value) is int


def _refuse_constant(name: str) -> Any:
    raise ValueError(f"{name} is not JSON")


def decode(raw: str | bytes) -> Envelope:
    ""
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
    ""
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
    ""
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


#


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


#
MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+=@-]{0,127}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
SHORT_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}")
RUNTIME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,199}")
ENDPOINT_HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9.:-]{0,252}")
#
ROLES = ("head", "worker")
#
MAX_ENDPOINTS = 8
#
MAX_FEATURES = 16


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
    _bounded(model.embd_bytes, 1, MAX_MODEL_BYTES, "models.embd_bytes")
    _bounded(model.output_bytes, 0, MAX_MODEL_BYTES, "models.output_bytes")
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
        "embd_bytes",
        "output_bytes",
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
    _need(
        len(offer.features) <= MAX_FEATURES
        and len(set(offer.features)) == len(offer.features)
        and all(TAG.fullmatch(feature) for feature in offer.features),
        "capabilities.features: not distinct tags",
    )
    capabilities: dict[str, Any] = {"roles": list(offer.roles)}
    if offer.runtime is not None:
        capabilities["runtime"] = offer.runtime
    if offer.features:
        capabilities["features"] = list(offer.features)
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
    ""
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
    ""
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
    ""
    _need(bool(TAG.fullmatch(code)), "code: not an error code")
    return _frame(
        "error", message_id, {"code": code, "message": message[:MAX_ERROR_TEXT]}, re
    )
