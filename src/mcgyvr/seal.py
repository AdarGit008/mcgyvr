"""Seal a ride end to end: the rider's request for one unit, its answer for the rider.

A hitchhike rung's host advertises a key for its unit (:class:`HostKey`, one per run of
its agent); the hub lists it with the rung, and the rider seals every request to it
(:func:`seal_request`). The hub carries the envelope without opening it, and the
host's agent opens it (:meth:`HostKey.open`), posts the request to the unit
(:func:`unit_body` holds it to the fields the hub would have passed) and seals the
answer back, event by event (:class:`AnswerSealer`). The rider opens each event
(:class:`AnswerOpener`) and reads the answer as it would a clear one.

The cipher, :data:`mcgyvr.hubwire.SEAL_SUITE`:

* the rider makes an X25519 key pair for the one request and agrees a secret with
  the unit's key; HKDF-SHA256 (salt: the two public keys, info: :data:`_INFO`) turns
  it into two keys, one per direction;
* the request is sealed with ChaCha20-Poly1305 under the request key, a random
  nonce and the key id it is for as associated data;
* each event of the answer is sealed under the answer key with a random nonce and
  its place in the answer (a counter from 0) as associated data, so an event the
  hub drops, repeats or reorders does not open. The nonce is random and not the
  counter itself: a hub that sends the same sealed request twice gets two answers
  under one answer key, and counter nonces would then repeat.

What stays in clear: the model asked for, whether the request streams, and of the
answer the model it names and its token counts
(:data:`mcgyvr.hubwire.SEALED_ANSWER_CLEAR_FIELDS`), which the hub charges by. The
host's agent and the unit behind it read the request in clear: sealing keeps the
hub out, not the host.

``cryptography`` is imported on first use, so a command that seals nothing does
not pay for loading it.
"""

from __future__ import annotations

import base64
import binascii
import functools
import hashlib
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mcgyvr import hubwire, whole

if TYPE_CHECKING:  # pragma: no cover - typing only
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

#: What the two direction keys are derived for, as HKDF's info.
_INFO = b"mcgyvr seal v1"
#: The associated data a request is sealed under, before its key id.
_REQUEST_AAD = b"mcgyvr seal v1 request "
#: The associated data an answer's event is sealed under, before its place.
_ANSWER_AAD = b"mcgyvr seal v1 answer "
_KEY_BYTES = 32
_NONCE_BYTES = 12
_TAG_BYTES = 16
#: The most bytes of an answer's sealed stream held back while an event is not yet
#: whole, as :class:`mcgyvr.whole.Whole` holds an event of the stream it assembles.
MAX_EVENT_BYTES = whole.MAX_EVENT_BYTES


class SealError(ValueError):
    """A sealed message that does not open, or is not of its shape.

    Tampered with, sealed to another key, out of its place in the answer, or a clear
    event where a sealed answer has only sealed ones.
    """


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: object, pattern: Any, field: str) -> bytes:
    if not isinstance(text, str) or not pattern.fullmatch(text):
        raise SealError(f"{field}: not of its shape")
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SealError(f"{field}: not base64") from exc


def key_id(public: bytes) -> str:
    """The id of the seal key whose public half is ``public``."""
    return hashlib.sha256(public).hexdigest()[:32]


def _directions(shared: bytes, ephemeral: bytes, public: bytes) -> tuple[bytes, bytes]:
    """The request key and the answer key one agreed secret gives."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    keys = HKDF(
        algorithm=hashes.SHA256(),
        length=2 * _KEY_BYTES,
        salt=ephemeral + public,
        info=_INFO,
    ).derive(shared)
    return keys[:_KEY_BYTES], keys[_KEY_BYTES:]


def _answer_aad(place: int) -> bytes:
    return _ANSWER_AAD + place.to_bytes(8, "big")


@dataclass(frozen=True)
class SealKey:
    """The key a unit advertises, as a rider holds it: its id and public half."""

    kid: str
    pub: str

    def __post_init__(self) -> None:
        if not isinstance(self.kid, str) or not hubwire.SEAL_KEY_ID.fullmatch(self.kid):
            raise ValueError("kid: not a seal key id")
        public = _unb64(self.pub, hubwire.SEAL_PUBLIC_KEY, "pub")
        if key_id(public) != self.kid:
            raise ValueError("kid: not the id of this key")

    @classmethod
    def of(cls, raw: object) -> SealKey:
        """The key a listing or an advert carries (``{"kid", "pub", "sig"?}``).

        Raises ValueError for one not of that shape; a field beyond
        :data:`~mcgyvr.hubwire.SEAL_KEY_FIELDS` is ignored. ``sig`` is the slot for
        the rig's signature over the key: its shape is checked, its value not yet.
        """
        if not isinstance(raw, Mapping):
            raise ValueError("seal: not an object")
        # A field this product does not know (one a later rig identity adds
        # beside ``sig``) is left unread, not refused: refusing it would refuse
        # the whole listing it came in.
        sig = raw.get("sig")
        if sig is not None and (
            not isinstance(sig, str) or not hubwire.SEAL_SIGNATURE.fullmatch(sig)
        ):
            raise ValueError("seal.sig: not of its shape")
        return cls(kid=raw.get("kid"), pub=raw.get("pub"))  # type: ignore[arg-type]

    def wire(self) -> dict[str, str]:
        return {"kid": self.kid, "pub": self.pub}


class HostKey:
    """The key a host's agent opens sealed rides with: made new each run, held in
    memory only, never written."""

    def __init__(self, private: X25519PrivateKey | None = None) -> None:
        self._given = private

    @functools.cached_property
    def _private(self) -> X25519PrivateKey:
        """Made on first use, so an agent that hosts nothing loads no cipher."""
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

        return self._given or X25519PrivateKey.generate()

    @functools.cached_property
    def _public(self) -> bytes:
        return self._private.public_key().public_bytes_raw()

    @functools.cached_property
    def unit_key(self) -> SealKey:
        return SealKey(kid=key_id(self._public), pub=_b64(self._public))

    @property
    def kid(self) -> str:
        return self.unit_key.kid

    def open(self, sealed: object) -> tuple[bytes, AnswerSealer]:
        """The request body a sealed envelope holds, and the sealer of its answer.

        Raises :class:`SealError` for an envelope not of its shape, one sealed to
        another key, or one that does not open.
        """
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

        if not isinstance(sealed, Mapping):
            raise SealError("sealed: not an object")
        if set(sealed) != set(hubwire.SEAL_ENVELOPE_FIELDS):
            raise SealError("sealed: not the envelope's fields")
        if sealed["v"] != hubwire.SEAL_VERSION or isinstance(sealed["v"], bool):
            raise SealError("sealed.v: not a version this agent opens")
        if sealed["to"] != self.kid:
            raise SealError("sealed.to: another key")
        ephemeral = _unb64(sealed["epk"], hubwire.SEAL_PUBLIC_KEY, "sealed.epk")
        nonce = _unb64(sealed["nonce"], hubwire.SEAL_NONCE, "sealed.nonce")
        text = sealed["ct"]
        if isinstance(text, str) and len(text) > hubwire.SEAL_MAX_CIPHERTEXT:
            raise SealError("sealed.ct: over the limit")
        ciphertext = _unb64(text, hubwire.SEAL_CIPHERTEXT, "sealed.ct")
        try:
            shared = self._private.exchange(
                X25519PublicKey.from_public_bytes(ephemeral)
            )
        except ValueError as exc:  # a low-order point: no secret agreed
            raise SealError("sealed.epk: no key agreed with it") from exc
        asking, answering = _directions(shared, ephemeral, self._public)
        try:
            body = ChaCha20Poly1305(asking).decrypt(
                nonce, ciphertext, _REQUEST_AAD + self.kid.encode()
            )
        except InvalidTag as exc:
            raise SealError("sealed: does not open") from exc
        return body, AnswerSealer(answering)


def seal_request(
    request: Mapping[str, Any], key: SealKey
) -> tuple[dict[str, Any], AnswerOpener]:
    """The sealed request for ``request`` to the unit holding ``key``, and the
    opener of its answer.

    ``request`` is sealed whole as compact JSON; in clear go only its ``model``,
    ``stream`` and ``stream_options`` (:data:`mcgyvr.hubwire.SEALED_CLEAR_FIELDS`).
    """
    from cryptography.hazmat.primitives.asymmetric.x25519 import (
        X25519PrivateKey,
        X25519PublicKey,
    )
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

    public = base64.b64decode(key.pub)
    mine = X25519PrivateKey.generate()
    ephemeral = mine.public_key().public_bytes_raw()
    shared = mine.exchange(X25519PublicKey.from_public_bytes(public))
    asking, answering = _directions(shared, ephemeral, public)
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = ChaCha20Poly1305(asking).encrypt(
        nonce, whole.dump(dict(request)), _REQUEST_AAD + key.kid.encode()
    )
    sealed: dict[str, Any] = {
        field: request[field]
        for field in sorted(hubwire.SEALED_CLEAR_FIELDS - {hubwire.SEALED_FIELD})
        if field in request
    }
    sealed[hubwire.SEALED_FIELD] = {
        "v": hubwire.SEAL_VERSION,
        "to": key.kid,
        "epk": _b64(ephemeral),
        "nonce": _b64(nonce),
        "ct": _b64(ciphertext),
    }
    return sealed, AnswerOpener(answering)


def unit_body(
    body: bytes, *, model: str, max_tokens: int | None, stream: bool
) -> bytes:
    """The request a host's agent posts to its unit for an opened sealed ride.

    The hub cannot hold a sealed request to the fields it passes a unit, so the agent
    does, as the hub does for one in clear: only :data:`mcgyvr.hubwire.FORWARDED_FIELDS`
    pass, ``max_completion_tokens`` folds into ``max_tokens``, ``n`` is 1 or absent,
    ``chat_template_kwargs`` keeps only :data:`mcgyvr.hubwire.CHAT_TEMPLATE_KEYS`,
    ``top_logprobs`` only with ``logprobs``. Every value is held to the bounds the hub
    holds a request in clear to (:func:`held_to_bounds`): a body outside them reaches
    no unit.
    The model is the unit's own, whatever the rider named; ``max_tokens`` is held to
    the hub's cap ``max_tokens``, which the hub sends in clear; ``stream`` is what the
    hub relays the answer as, and a stream asks for its usage. Raises
    :class:`SealError` for a body that is not a chat request within those bounds.
    """
    try:
        asked = json.loads(body)
    except (ValueError, RecursionError) as exc:
        raise SealError("the sealed request is not JSON") from exc
    if not isinstance(asked, dict):
        raise SealError("the sealed request is not an object")
    if asked.get("n") is not None and not _within(asked.get("n"), 1, 1):
        raise SealError("the sealed request asks for more than one choice")
    asked = held_to_bounds(asked)
    passed = hubwire.FORWARDED_FIELDS - {"max_completion_tokens", "n"}
    request = {key: value for key, value in asked.items() if key in passed}
    wanted = asked.get("max_tokens") or asked.get("max_completion_tokens")
    caps = [cap for cap in (wanted, max_tokens) if cap is not None]
    request.pop("max_tokens", None)
    if caps:
        request["max_tokens"] = min(caps)
    knobs = request.pop("chat_template_kwargs", None)
    if isinstance(knobs, dict):
        kept = {k: v for k, v in knobs.items() if k in hubwire.CHAT_TEMPLATE_KEYS}
        if kept:
            request["chat_template_kwargs"] = kept
    if request.get("logprobs") is not True:
        request.pop("top_logprobs", None)
    request["model"] = model
    request["stream"] = stream
    if stream:
        request = whole.asking(request)
    else:
        request.pop("stream_options", None)
    return whole.dump(request)


def _whole(value: object) -> bool:
    return type(value) is int


def _within(value: object, low: float, high: float, *, whole: bool = True) -> bool:
    """Whether ``value`` is a number (a whole one when ``whole``; never a bool)
    from ``low`` to ``high``."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return low <= value <= high
    return not whole and isinstance(value, float) and low <= value <= high


def _optional(asked: Mapping[str, Any], field: str, fits: bool) -> None:
    if asked.get(field) is not None and not fits:
        raise SealError(f"the sealed request's {field} is not one the hub passes")


def held_to_bounds(asked: dict[str, Any]) -> dict[str, Any]:
    """``asked`` held to the bounds a chat request in clear is held to on the hub
    (``hubwire.CHAT_MAX_*``, :data:`~mcgyvr.hubwire.MESSAGE_ROLES`,
    :data:`~mcgyvr.hubwire.CHAT_RANGES`), its messages kept to
    :data:`~mcgyvr.hubwire.MESSAGE_FIELDS` as the hub drops any other. Raises
    :class:`SealError` for a value the hub would refuse."""
    messages = asked.get("messages")
    if (
        not isinstance(messages, list)
        or not messages
        or len(messages) > hubwire.CHAT_MAX_MESSAGES
    ):
        raise SealError(
            "the sealed request has no messages, or more than the hub passes"
        )
    asked = {**asked, "messages": [_message(m) for m in messages]}
    for field in ("max_tokens", "max_completion_tokens"):
        _optional(asked, field, _within(asked.get(field), 1, float("inf")))
    for field, (low, high, whole_only) in hubwire.CHAT_RANGES.items():
        _optional(asked, field, _within(asked.get(field), low, high, whole=whole_only))
    stop = asked.get("stop")
    _optional(
        asked,
        "stop",
        isinstance(stop, str)
        or (
            isinstance(stop, list)
            and len(stop) <= hubwire.CHAT_MAX_STOP
            and all(isinstance(s, str) for s in stop)
        ),
    )
    tools = asked.get("tools")
    _optional(asked, "tools", _dicts(tools, hubwire.CHAT_MAX_TOOLS))
    _optional(asked, "seed", _whole(asked.get("seed")))
    _optional(asked, "stream_options", isinstance(asked.get("stream_options"), dict))
    _optional(asked, "response_format", isinstance(asked.get("response_format"), dict))
    _optional(asked, "tool_choice", isinstance(asked.get("tool_choice"), str | dict))
    _optional(asked, "logprobs", type(asked.get("logprobs")) is bool)
    top = asked.get("top_logprobs")
    _optional(asked, "top_logprobs", _within(top, 0, hubwire.CHAT_MAX_TOP_LOGPROBS))
    knobs = asked.get("chat_template_kwargs")
    _optional(asked, "chat_template_kwargs", isinstance(knobs, dict))
    if isinstance(knobs, dict):
        _optional(knobs, "enable_thinking", type(knobs.get("enable_thinking")) is bool)
    return asked


def _dicts(value: object, most: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) <= most
        and all(isinstance(item, dict) for item in value)
    )


def _message(message: object) -> dict[str, Any]:
    """One message held to the hub's bounds, with only the fields it passes."""
    if not isinstance(message, dict) or "content" not in message:
        raise SealError("a sealed message is not a message")
    if message.get("role") not in hubwire.MESSAGE_ROLES:
        raise SealError("a sealed message's role is not one the hub passes")
    content = message["content"]
    if not (
        content is None
        or isinstance(content, str)
        or (isinstance(content, list) and _dicts(content, len(content)))
    ):
        raise SealError("a sealed message's content is not text or parts")
    name, call = message.get("name"), message.get("tool_call_id")
    _optional(
        message, "name", isinstance(name, str) and len(name) <= hubwire.CHAT_MAX_NAME
    )
    _optional(
        message,
        "tool_call_id",
        isinstance(call, str) and len(call) <= hubwire.CHAT_MAX_TOOL_CALL_ID,
    )
    _optional(
        message, "tool_calls", _dicts(message.get("tool_calls"), hubwire.CHAT_MAX_TOOLS)
    )
    return {k: v for k, v in message.items() if k in hubwire.MESSAGE_FIELDS}


def _events(held: bytearray, chunk: bytes) -> list[bytes]:
    """The events ``chunk`` completes (:func:`mcgyvr.whole.cut_events`)."""
    try:
        return whole.cut_events(held, chunk)
    except ValueError as exc:
        raise SealError(str(exc)) from exc


def _object(data: bytes | None) -> dict[str, Any] | None:
    if data is None:
        return None
    try:
        value = json.loads(data)
    except (ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


class AnswerSealer:
    """Seals one answer, event by event, for the rider whose request it opened."""

    def __init__(self, key: bytes) -> None:
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

        self._aead = ChaCha20Poly1305(key)
        self._place = 0
        self._held = bytearray()
        self._ended = False
        self._model: str | None = None  # the stream's, read off its first event

    def _seal(self, plain: bytes) -> dict[str, str]:
        nonce = os.urandom(_NONCE_BYTES)
        sealed = self._aead.encrypt(nonce, plain, _answer_aad(self._place))
        self._place += 1
        return {"nonce": _b64(nonce), "ct": _b64(sealed)}

    def _wrapped(self, plain: bytes, document: dict[str, Any] | None) -> bytes:
        clear = {
            field: document[field]
            for field in hubwire.SEALED_ANSWER_CLEAR_FIELDS
            if document is not None and field in document
        }
        clear[hubwire.SEALED_FIELD] = self._seal(plain)
        return whole.dump(clear)

    def body(self, body: bytes) -> bytes:
        """A whole answer (or error body) sealed as one JSON object."""
        return self._wrapped(body, _object(body))

    def _event(self, event: bytes) -> bytes:
        data = whole.field_of(event, b"data")
        if data is not None and data.strip() == whole.DONE:
            return b"data: " + whole.DONE + b"\n\n"
        if not event.strip():
            return b""
        # An event is read for its clear fields only where it can hold more than
        # the model already read: the first one, and one that counts tokens.
        if self._model is None or (
            data is not None and (b'"usage"' in data or b'"timings"' in data)
        ):
            document = _object(data)
            if self._model is None and document is not None:
                model = document.get("model")
                self._model = model if isinstance(model, str) else ""
        else:
            document = {"model": self._model} if self._model else None
        return b"data: " + self._wrapped(event, document) + b"\n\n"

    def feed(self, chunk: bytes) -> bytes:
        """The sealed events ``chunk`` completes of a streamed answer."""
        return b"".join(self._event(event) for event in _events(self._held, chunk))

    def end(self) -> bytes:
        """What is left at the end of the stream, an event never closed, sealed."""
        if self._ended:
            return b""
        self._ended = True
        rest, self._held = bytes(self._held), bytearray()
        return self._event(rest) if rest.strip() else b""

    def reader(
        self, read1: Callable[[int], bytes], step: int
    ) -> Callable[[int], bytes]:
        """A ``read1`` over the sealed stream of the one ``read1`` reads, ``step``
        bytes at a time: each call returns what one read of the source seals to, at
        most the bytes asked for, and nothing once the source and the seal are done."""
        out = bytearray()

        def read(most: int) -> bytes:
            while not out and not self._ended:
                raw = read1(step)
                out.extend(self.feed(raw) if raw else self.end())
            taken = bytes(out[:most])
            del out[:most]
            return taken

        return read


class AnswerOpener:
    """Opens one sealed answer, event by event, for the rider who sealed its request."""

    def __init__(self, key: bytes) -> None:
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

        self._aead = ChaCha20Poly1305(key)
        self._place = 0
        self._held = bytearray()

    def _open(self, document: dict[str, Any]) -> bytes:
        from cryptography.exceptions import InvalidTag

        sealed = document.get(hubwire.SEALED_FIELD)
        if not isinstance(sealed, dict) or set(sealed) != set(
            hubwire.SEALED_ANSWER_ENVELOPE_FIELDS
        ):
            raise SealError("sealed: not an answer's envelope")
        nonce = _unb64(sealed["nonce"], hubwire.SEAL_NONCE, "sealed.nonce")
        ciphertext = _unb64(sealed["ct"], hubwire.SEAL_CIPHERTEXT, "sealed.ct")
        try:
            plain = self._aead.decrypt(nonce, ciphertext, _answer_aad(self._place))
        except InvalidTag as exc:
            raise SealError(
                f"the answer's event {self._place} does not open in its place"
            ) from exc
        self._place += 1
        return plain

    @staticmethod
    def _named(plain: bytes, document: dict[str, Any], data: bool) -> bytes:
        """``plain`` under the model the clear ``document`` names: the hub writes
        there the name the answer goes out under, as it does in a clear answer."""
        model = document.get("model")
        if data and (not plain.startswith(b"data:") or b"\n" in plain.strip()):
            return plain  # not one data line: passed as the host's agent sealed it
        if not isinstance(model, str) or b'"model":' + whole.dump(model) in plain:
            return plain  # no name written over it, or the one it already has
        inner = _object(whole.field_of(plain, b"data") if data else plain)
        if not isinstance(model, str) or inner is None or "model" not in inner:
            return plain
        inner["model"] = model
        return (b"data: " if data else b"") + whole.dump(inner)

    @staticmethod
    def _clear_error(document: dict[str, Any] | None) -> bool:
        """Whether a clear document is one the hub may write in a sealed answer: an
        error, of its own (a refusal, a stream it cut) and holding no answer."""
        return (
            document is not None
            and isinstance(document.get("error"), dict)
            and "choices" not in document
            and hubwire.SEALED_FIELD not in document
        )

    def body(self, body: bytes) -> bytes:
        """The answer a whole sealed body holds; a clear error passes as it is."""
        document = _object(body)
        if self._clear_error(document):
            return body
        if document is None or hubwire.SEALED_FIELD not in document:
            raise SealError("a clear answer to a sealed request")
        return self._named(self._open(document), document, data=False)

    def _event(self, event: bytes) -> bytes:
        data = whole.field_of(event, b"data")
        if data is None:
            if not event.strip() or all(
                line.startswith(b":") for line in event.split(b"\n") if line.strip()
            ):
                return b""  # nothing but comments: a keepalive
            raise SealError("a clear event in a sealed answer")
        if data.strip() == whole.DONE:
            return b"data: " + whole.DONE + b"\n\n"
        document = _object(data)
        if self._clear_error(document):
            return event + b"\n\n"
        if document is None or hubwire.SEALED_FIELD not in document:
            raise SealError("a clear event in a sealed answer")
        return self._named(self._open(document), document, data=True) + b"\n\n"

    def feed(self, chunk: bytes) -> bytes:
        """The opened events ``chunk`` completes of a sealed stream."""
        return b"".join(self._event(event) for event in _events(self._held, chunk))

    def end(self) -> bytes:
        """What is left at the end of the stream, an event never closed, opened."""
        rest, self._held = bytes(self._held), bytearray()
        return self._event(rest) if rest.strip() else b""
