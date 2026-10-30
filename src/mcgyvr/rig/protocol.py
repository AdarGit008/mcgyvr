"""The rig agent's half of the hub's agent protocol, version 1.

A frame is one JSON object, one websocket text frame: ``v``, ``type``, ``id``,
an optional ``re`` naming the message this one answers, and a ``body``. The
limits, name shapes and close and error codes below are the ones the hub's
published schema holds, and the builders here write the frames an agent sends
(``hello``, ``heartbeat``, ``error``) while ``decode`` and the readers take the
frames it receives.

A builder checks its arguments and raises ``ValueError`` naming the field at
fault rather than write a frame the hub would refuse, and a reader raises
``ProtocolError`` carrying the code to answer with.
"""

from __future__ import annotations

import dataclasses
import enum
import json
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from mcgyvr import hubwire

#: The version this agent writes in ``v`` and the only one it reads: another
#: number is refused as ``unsupported_version``.
PROTOCOL_VERSION = 1
#: Largest frame, in bytes of UTF-8, that this agent reads or writes.
MAX_MESSAGE_BYTES = 64 * 1024
#: Frames per second one agent may send over its channel.
#: The agent paces itself at half this, so it stays well inside the limit.
MAX_FRAMES_PER_SECOND = 100
#: Most cards one hello or one heartbeat may report (the wire's,
#: :mod:`mcgyvr.hubwire`).
MAX_CARDS = hubwire.MAX_CARDS
#: Highest card index a report may name; indexes start at 0 and no card may be
#: reported twice in one frame.
MAX_CARD_INDEX = hubwire.MAX_RESOURCE_INDEX
#: Longest card name, in characters, a report may carry.
CARD_NAME_MAX = hubwire.RESOURCE_NAME_MAX
#: Upper bound on any RAM or VRAM figure in a frame, counted in MiB.
MAX_MB = hubwire.RESOURCE_MAX_MB
#: Longest error text, in characters: a longer one is cut to this before it is
#: sent, and a received one longer than this is refused.
MAX_ERROR_TEXT = 500
#: The seconds a hub may set as the heartbeat interval in an ack.
HEARTBEAT_INTERVAL_S = (1, 3600)
#: Most models a hello may name.
MAX_MODELS = 64
#: Most live session ids a hello may list.
MAX_SESSIONS_REPORTED = 4
#: Upper bound on a model file's size, and on the bytes one of its tensors takes.
MAX_MODEL_BYTES = 1 << 50
#: Upper bound on a model's layer count.
#: Upper bound on a model's context length and on its embedding and head counts.
MAX_LAYERS = 4096
MAX_COUNT = 1 << 20
#: Upper bound on the key and value cache a model spends per token.
MAX_KV_BYTES_PER_TOKEN = 1 << 30

#: The shapes the envelope's own fields take: message ids, type tags (which also
#: serve as error codes, endpoint kinds and feature names), machine ids and
#: agent versions.
MESSAGE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
TAG = re.compile(r"[a-z][a-z0-9_]{0,63}")
MACHINE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
AGENT_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}")
#: A card name is text a hub may show, so it excludes control characters,
#: C1 controls, the bidi embedding and override marks and the bidi isolates: a
#: name from a driver cannot reorder or hide what a hub draws around it. It is
#: a resource's name rule (:data:`mcgyvr.hubwire.RESOURCE_NAME`).
CARD_NAME = hubwire.RESOURCE_NAME


class CloseCode(enum.IntEnum):
    """The codes a hub closes the channel with, as the wire spells them.

    The values are the hub's: 1008 is the websocket's own policy violation, and
    4001 onwards are the hub's own reasons.
    """

    POLICY = 1008  # the channel broke the websocket's rules, e.g. too many frames
    REVOKED = 4001  # the hub revoked this rig's token
    TIMEOUT = 4008  # this agent's heartbeats stopped reaching the hub
    SUPERSEDED = 4009  # another agent took this rig over with the same token


class ErrorCode(enum.StrEnum):
    """The error codes this agent and the hub send in an ``error`` frame.

    A reader accepts any type tag as a code, so this is what the two sides name
    rather than the whole set a hub may send; the agent stops on the refusals
    it cannot retry and keeps retrying after the rest.
    """

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
    """A frame that broke the protocol, said in the terms an error frame uses.

    ``code`` is the code to answer with, ``message`` the text to show, cut to
    ``MAX_ERROR_TEXT`` characters, and ``re`` the id of the message at fault,
    left None when the frame was too broken to name one.
    """

    def __init__(self, code: str, message: str, re: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message[:MAX_ERROR_TEXT]
        self.re = re


@dataclass(frozen=True, kw_only=True)
class Envelope:
    """One frame as it arrived: its type tag, its id, the id it answers, its body.

    ``body`` is the JSON object as decoded, with nothing checked in it; the
    reader for the envelope's type checks the fields it needs.
    """

    type: str
    id: str
    re: str | None
    body: Mapping[str, Any]


@dataclass(frozen=True, kw_only=True)
class Ack:
    """A hub's answer to a hello or a heartbeat.

    ``rig_id`` is the rig the hub bound this agent to and
    ``heartbeat_interval_s`` how often it wants heartbeats from now on; the
    hub may leave either out, and then the agent keeps what it had.
    """

    re: str
    rig_id: str | None
    heartbeat_interval_s: int | None
    #: What the member chose on the hub for this rig to lend
    #: (:data:`mcgyvr.hubwire.LENDING_FIELD`), when the hub says.
    lending: hubwire.Lending | None = None
    #: Why a lending the hub sent was not taken (not the wire's shape), so the
    #: rig lends as its own settings say; None when there was none to refuse.
    lending_unread: str | None = None


@dataclass(frozen=True, kw_only=True)
class Error:
    """An ``error`` frame's body: the code, the text to show, and what it answers."""

    re: str | None
    code: str
    message: str


@dataclass(frozen=True, kw_only=True)
class CardReport:
    """One card as a hello reports it: its index, its name and its VRAM in MiB."""

    index: int
    name: str
    vram_total_mb: int
    vram_free_mb: int


@dataclass(frozen=True, kw_only=True)
class ModelInfo:
    """A model file a hello offers, with what planning needs from its header.

    ``size_bytes`` is the file's size and ``digest`` its sha256, when the agent
    has one. The rest come from the file's header: the architecture, the layer
    and training context counts, the embedding and head counts, the key and
    value cache one token costs, and the bytes the token embedding and output
    tensors take. A field the header does not give is None and goes unspoken on
    the wire.
    """

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
    #: The bytes the token embedding tensor and the output tensor take. A model
    #: whose output tensor is tied to its embedding has no output tensor of its
    #: own and carries 0 here, while a header that names neither leaves both None.
    embd_bytes: int | None = None
    output_bytes: int | None = None


@dataclass(frozen=True, kw_only=True)
class Offer:
    """What an agent can do with its rig, as a hello advertises it.

    ``roles`` are the ones it takes: ``head`` serves a session's model and
    ``worker`` lends hardware to one. ``runtime`` names the inference runtime
    and ``features`` the behaviours the agent speaks, while ``endpoints`` are
    candidate addresses peers may reach the rig's tunnel on, ``models`` the
    files it can serve, and ``sessions`` the ids of the sessions it is in now.
    ``rpc_proto`` is the llama.cpp RPC protocol its runtime speaks, when the
    agent knows it (the pinned build), sent as
    :data:`mcgyvr.hubwire.RPC_PROTO_FIELD` among the capabilities.
    """

    roles: tuple[str, ...]
    runtime: str | None
    endpoints: tuple[tuple[str, int, str], ...]  # (host, port, kind) of one candidate
    models: tuple[ModelInfo, ...]
    sessions: tuple[str, ...]
    features: tuple[str, ...] = ()
    rpc_proto: hubwire.RpcProto | None = None


@dataclass(frozen=True, kw_only=True)
class CardReading:
    """One card in a heartbeat: its index and the VRAM it has free, in MiB."""

    index: int
    vram_free_mb: int


def new_id() -> str:
    """A fresh message id: 32 hex digits, which ``MESSAGE_ID`` allows."""
    return uuid.uuid4().hex


def _is_int(value: object) -> bool:
    return type(value) is int


def _refuse_constant(name: str) -> Any:
    raise ValueError(f"{name} is not JSON")


def decode(raw: str | bytes) -> Envelope:
    """Read one frame into an ``Envelope``, refusing what is not of the wire.

    ``raw`` may be text or UTF-8 bytes, and either way it must be one JSON
    object of at most ``MAX_MESSAGE_BYTES`` with this version, a type tag, a
    valid message id and, when it has one, a ``re`` naming a message id. A
    frame without a body reads as an empty one, and NaN or Infinity is refused
    as not JSON. Every refusal is a ``ProtocolError``, naming the frame's id as
    the message to answer whenever that id was readable.
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
    """Read an ack's body: the rig id, the beat interval the hub set, and
    what the member chose for the rig to lend.

    The frame must answer a message, so ``re`` cannot be missing.
    ``rig_id``, ``heartbeat_interval_s`` and the lending may be left out, and
    an interval must be a whole number of seconds within
    ``HEARTBEAT_INTERVAL_S``. A lending that does not keep
    :meth:`mcgyvr.hubwire.Lending.validate`'s rules, or leaves a field out, is
    not taken, and the ack says why (``lending_unread``): the rig then lends as
    its own settings say.
    """
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
    lending, unread = _lending(envelope.body.get(hubwire.LENDING_FIELD))
    return Ack(
        re=envelope.re,
        rig_id=rig_id,
        heartbeat_interval_s=interval,
        lending=lending,
        lending_unread=unread,
    )


def _lending(raw: object) -> tuple[hubwire.Lending | None, str | None]:
    """An ack's :class:`mcgyvr.hubwire.Lending` held to its rules, or None
    with why it is not taken. Every field must be there: ``cards`` null is
    every card and an empty list none, while a missing ``cards`` is no
    lending at all (never read as every card). None, None when the hub sent
    none."""
    if raw is None:
        return None, None
    where = f"{hubwire.LENDING_FIELD}"
    names = {f.name for f in dataclasses.fields(hubwire.Lending)}
    if not isinstance(raw, Mapping):
        return None, f"{where}: not an object"
    missing = sorted(names - set(raw))
    if missing:
        return None, f"{where}: no {', '.join(missing)}"
    cards = raw["cards"]
    if cards is not None and not isinstance(cards, list):
        return None, f"{where}.cards: not null or a list"
    lending = hubwire.Lending(
        cards=None if cards is None else tuple(cards),
        ram_mb=raw["ram_mb"],
        cpu_cores=raw["cpu_cores"],
    )
    try:
        lending.validate()
    except (TypeError, ValueError) as exc:
        return None, f"{where}.{exc}"
    return lending, None


def read_error(envelope: Envelope) -> Error:
    """Read an error frame's body: its code and the text to show.

    The code must be a type tag and the message, when it gives one, text of at
    most ``MAX_ERROR_TEXT`` characters; an error may answer a message or come
    on its own, so ``re`` is passed through as it stands.
    """
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


# What the builders share: a check that raises ValueError naming the field at
# fault, and the checks for the bounded values a hello and a heartbeat carry.


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


#: The shapes of what an offer names: model names (the wire's,
#: :mod:`mcgyvr.hubwire`), digests, architectures, runtimes and endpoint hosts,
#: at the patterns the hub's schema holds.
MODEL_NAME = hubwire.MODEL_NAME
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
SHORT_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}")
RUNTIME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,199}")
ENDPOINT_HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9.:-]{0,252}")
#: The roles an agent may offer, and the most it may offer at once.
ROLES = ("head", "worker")
#: Most endpoints one offer may name.
MAX_ENDPOINTS = 8
#: Most features one offer may name.
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
    if offer.rpc_proto is not None:
        try:
            offer.rpc_proto.validate()
        except ValueError as exc:
            raise ValueError(f"capabilities.{hubwire.RPC_PROTO_FIELD}: {exc}") from exc
        capabilities[hubwire.RPC_PROTO_FIELD] = asdict(offer.rpc_proto)
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
    resources: Sequence[hubwire.Resource] = (),
    host: hubwire.Host | None = None,
) -> str:
    """A ``hello`` frame: what this machine is, and what it offers.

    ``machine_id`` and ``agent_version`` name the machine and the agent build,
    ``ram_total_mb`` and ``ram_free_mb`` are MiB of memory, and ``cards`` are
    the cards with their names and their VRAM in MiB. An ``offer`` adds the
    capabilities, endpoints, models and sessions the rig brings; left out, the
    frame says nothing about them. Free RAM is left out when it is None, and a
    card with more free VRAM than it has in total is refused.

    ``resources`` are what the rig lends (:class:`mcgyvr.hubwire.Resource`),
    left out when there are none; with them, ``cards`` must be exactly the
    cards they make (:func:`mcgyvr.hubwire.cards_from_resources`), as the hub
    refuses any other. ``host`` names the system the rig runs on.
    """
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
    if resources:
        made = hubwire.cards_from_resources(resources)  # it holds them to fit
        _need(
            body["cards"] == made,
            f"cards: not the cards the {' and '.join(hubwire.CARD_KINDS)} "
            "resources make",
        )
        body["resources"] = [asdict(resource) for resource in resources]
    if host is not None:
        host.validate()
        body["host"] = asdict(host)
    if offer is not None:
        body.update(_offer_body(offer))
    return _frame("hello", message_id, body, None)


def heartbeat(
    message_id: str,
    *,
    ram_free_mb: int | None,
    cards: Sequence[CardReading],
    resources: Sequence[hubwire.ResourceReading] = (),
) -> str:
    """A ``heartbeat`` frame: how much memory and VRAM is free right now.

    Free RAM is left out when it is None, and each card carries only its index
    and its free MiB. ``resources`` re-read the free MiB of what the hello
    lent, left out when there are none; with them, ``cards`` must be exactly
    the readings they make (:func:`mcgyvr.hubwire.card_readings_from`).
    """
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
    if resources:
        made = hubwire.card_readings_from(resources)  # it holds them to fit
        _need(
            body["cards"] == made,
            f"cards: not the readings the {' and '.join(hubwire.CARD_KINDS)} "
            "resources make",
        )
        body["resources"] = [asdict(reading) for reading in resources]
    return _frame("heartbeat", message_id, body, None)


def error(message_id: str, *, code: str, message: str, re: str | None) -> str:
    """An ``error`` frame: a type tag for the code, the text to show, what it answers.

    The text is cut to ``MAX_ERROR_TEXT`` characters, and ``re`` is None when
    the error answers nothing in particular.
    """
    _need(bool(TAG.fullmatch(code)), "code: not an error code")
    return _frame(
        "error", message_id, {"code": code, "message": message[:MAX_ERROR_TEXT]}, re
    )
