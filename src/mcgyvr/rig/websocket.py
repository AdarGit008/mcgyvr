"""A websocket client (RFC 6455) on the standard library, for the hub's channel.

The rig agent keeps one websocket open to its hub. The product's runtime takes
no dependency for that: this is the client half of the RFC and no more, over
``socket`` and ``ssl``. It offers no extension and no subprotocol, sends text
frames, answers pings, reassembles fragments, and closes the way the RFC says.

The server is not trusted. Every bound is checked before it is acted on: the
handshake answer is read up to :data:`MAX_HANDSHAKE_BYTES` and must be a
correct switch, a frame's announced length is refused past the caller's
``max_message`` before its payload is read, and a frame the RFC forbids a
server to send closes the channel with the RFC's code
(:class:`Close`). Every wait has a deadline, so a server that stalls is given
up on rather than waited for.

``wss://`` is TLS with the certificate and the host name checked
(:func:`default_ssl_context`).
"""

from __future__ import annotations

import base64
import contextlib
import enum
import hashlib
import os
import re
import socket
import ssl
import struct
import time
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass

#: The most bytes a handshake answer may take, status line and headers.
MAX_HANDSHAKE_BYTES = 16 * 1024
#: The RFC's constant a server proves it read the key with.
_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
#: The longest payload of a control frame (ping, pong, close).
_MAX_CONTROL = 125
#: How long a closing client waits for the server's own close, in seconds.
CLOSE_WAIT_S = 1.0

#: A header name or value that cannot break the request it is written into.
_TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
_VALUE = re.compile(r"[\t\x20-\x7e]*")


class Opcode(enum.IntEnum):
    """A frame's opcode."""

    CONTINUATION = 0
    TEXT = 1
    BINARY = 2
    CLOSE = 8
    PING = 9
    PONG = 10


class Close(enum.IntEnum):
    """The close codes this client sends, and the one that is never sent."""

    NORMAL = 1000
    PROTOCOL_ERROR = 1002
    INVALID_DATA = 1007
    TOO_BIG = 1009
    #: Never on the wire: a close frame that carried no code.
    NO_STATUS = 1005
    #: Never on the wire: the connection ended without a close frame.
    ABNORMAL = 1006


class WebSocketError(Exception):
    """The channel failed."""


class HandshakeError(WebSocketError):
    """The server did not switch to a websocket; ``status`` is its HTTP status
    when it answered with one."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ClosedError(WebSocketError):
    """The channel is closed: ``code`` and ``reason`` are the close's, and
    ``by_peer`` says whether the server closed it."""

    def __init__(self, code: int, reason: str, *, by_peer: bool) -> None:
        super().__init__(f"closed with {code}" + (f": {reason}" if reason else ""))
        self.code = code
        self.reason = reason
        self.by_peer = by_peer


class _ViolationError(Exception):
    def __init__(self, code: Close, why: str) -> None:
        super().__init__(why)
        self.code = code
        self.why = why


@dataclass(frozen=True, kw_only=True)
class Target:
    """Where a websocket URL points."""

    secure: bool
    host: str
    port: int
    path: str

    @property
    def authority(self) -> str:
        """The ``Host`` header: the port only when it is not the scheme's own."""
        host = f"[{self.host}]" if ":" in self.host else self.host
        default = 443 if self.secure else 80
        return host if self.port == default else f"{host}:{self.port}"


def parse_url(url: str) -> Target:
    """The target of a ``ws://`` or ``wss://`` URL, or ``ValueError``.

    A URL with credentials, a fragment, a bad port or a character a request
    line cannot carry is refused rather than repaired.
    """
    if not _VALUE.fullmatch(url) or " " in url or "\t" in url:
        raise ValueError("the URL holds a character a request cannot carry")
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ("ws", "wss"):
        raise ValueError("a websocket URL starts ws:// or wss://")
    if parts.username is not None or parts.password is not None:
        raise ValueError("a websocket URL carries no credentials")
    if parts.fragment or url.endswith("#"):
        raise ValueError("a websocket URL has no fragment")
    host = (parts.hostname or "").lower()
    if not host:
        raise ValueError("the URL names no host")
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("the URL's port is not a port") from exc
    secure = scheme == "wss"
    if port is None:
        port = 443 if secure else 80
    if not 0 < port < 65536:
        raise ValueError("the URL's port is not a port")
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return Target(secure=secure, host=host, port=port, path=path)


def default_ssl_context() -> ssl.SSLContext:
    """TLS as the hub is reached: the system's trust, the name checked."""
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def accept_key(key: str) -> str:
    """The ``Sec-WebSocket-Accept`` a server owes for ``key``."""
    digest = hashlib.sha1((key + _GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def _mask(key: bytes, data: bytes) -> bytes:
    size = len(data)
    if not size:
        return b""
    stream = (key * (size // 4 + 1))[:size]
    return (int.from_bytes(data, "big") ^ int.from_bytes(stream, "big")).to_bytes(
        size, "big"
    )


def encode_frame(opcode: Opcode, payload: bytes, key: bytes) -> bytes:
    """One final, masked client frame."""
    size = len(payload)
    first = 0x80 | opcode
    if size < 126:
        head = struct.pack("!BB", first, 0x80 | size)
    elif size < 1 << 16:
        head = struct.pack("!BBH", first, 0x80 | 126, size)
    else:
        head = struct.pack("!BBQ", first, 0x80 | 127, size)
    return head + key + _mask(key, payload)


@dataclass(frozen=True)
class _Frame:
    fin: bool
    opcode: int
    payload: bytes


def _parse_frame(buffer: bytes | bytearray, limit: int) -> tuple[_Frame, int] | None:
    """The first frame in ``buffer`` and its length, ``None`` when it is not
    all there yet, or :class:`_ViolationError`. The header is judged as soon as it
    is there, so a length past ``limit`` is refused before its payload."""
    if len(buffer) < 2:
        return None
    first, second = buffer[0], buffer[1]
    fin, rsv, opcode = bool(first & 0x80), first & 0x70, first & 0x0F
    if rsv:
        raise _ViolationError(Close.PROTOCOL_ERROR, "a reserved bit is set")
    if opcode not in Opcode.__members__.values():
        raise _ViolationError(Close.PROTOCOL_ERROR, "an unknown opcode")
    if second & 0x80:
        raise _ViolationError(Close.PROTOCOL_ERROR, "a server frame is masked")
    size, at = second & 0x7F, 2
    if size == 126:
        if len(buffer) < 4:
            return None
        (size,) = struct.unpack_from("!H", buffer, 2)
        at = 4
    elif size == 127:
        if len(buffer) < 10:
            return None
        (size,) = struct.unpack_from("!Q", buffer, 2)
        if size >> 63:
            raise _ViolationError(Close.PROTOCOL_ERROR, "a length with its top bit set")
        at = 10
    if opcode >= Opcode.CLOSE:
        if not fin:
            raise _ViolationError(Close.PROTOCOL_ERROR, "a fragmented control frame")
        if size > _MAX_CONTROL:
            raise _ViolationError(Close.PROTOCOL_ERROR, "a control frame too long")
    elif size > limit:
        raise _ViolationError(Close.TOO_BIG, "a frame past the message bound")
    if len(buffer) < at + size:
        return None
    return _Frame(fin, opcode, bytes(buffer[at : at + size])), at + size


def _close_payload(payload: bytes) -> tuple[int, str]:
    if not payload:
        return Close.NO_STATUS, ""
    if len(payload) == 1:
        raise _ViolationError(Close.PROTOCOL_ERROR, "a close of one byte")
    (code,) = struct.unpack("!H", payload[:2])
    if not (1000 <= code <= 1003 or 1007 <= code <= 1014 or 3000 <= code <= 4999):
        raise _ViolationError(Close.PROTOCOL_ERROR, "a close code no one sends")
    try:
        reason = payload[2:].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _ViolationError(Close.INVALID_DATA, "a close reason not UTF-8") from exc
    return code, reason


class WebSocket:
    """One open channel. Not thread-safe: one caller sends and receives."""

    def __init__(self, sock: socket.socket, *, max_message: int, buffer: bytes) -> None:
        self._sock = sock
        self._max = max_message
        self._buffer = bytearray(buffer)
        self._parts: list[bytes] = []
        self._kind: int | None = None
        self._closed: ClosedError | None = None

    # -- sending --

    def _send(self, opcode: Opcode, payload: bytes, timeout: float) -> None:
        if self._closed is not None:
            raise self._closed
        frame = encode_frame(opcode, payload, os.urandom(4))
        try:
            self._sock.settimeout(timeout)
            self._sock.sendall(frame)
        except OSError as exc:
            self._drop(Close.ABNORMAL, f"send failed: {exc.__class__.__name__}")
            raise self._closed or WebSocketError("send failed") from exc

    def send_text(self, text: str, *, timeout: float = 10.0) -> None:
        """Send ``text`` as one frame; ``ValueError`` past the message bound."""
        payload = text.encode("utf-8")
        if len(payload) > self._max:
            raise ValueError(f"a message of {len(payload)} bytes is past the bound")
        self._send(Opcode.TEXT, payload, timeout)

    # -- receiving --

    def receive(self, timeout: float) -> str | bytes | None:
        """The next message, or ``None`` when none is whole within ``timeout``
        seconds; :class:`ClosedError` once the channel is closed."""
        deadline = time.monotonic() + timeout
        while True:
            if self._closed is not None:
                raise self._closed
            try:
                frame = self._next_frame(deadline)
                if frame is None:
                    return None
                message = self._take(frame)
            except _ViolationError as violation:
                self._fail(violation.code, violation.why)
                continue
            if message is not None:
                return message

    def _next_frame(self, deadline: float) -> _Frame | None:
        while True:
            parsed = _parse_frame(self._buffer, self._max)
            if parsed is not None:
                frame, used = parsed
                del self._buffer[:used]
                return frame
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            try:
                self._sock.settimeout(left)
                chunk = self._sock.recv(65536)
            except TimeoutError:
                return None
            except OSError:
                chunk = b""
            if not chunk:
                self._drop(Close.ABNORMAL, "the connection dropped")
                raise self._closed or WebSocketError("dropped")
            self._buffer += chunk

    def _take(self, frame: _Frame) -> str | bytes | None:
        if frame.opcode == Opcode.PING:
            self._send(Opcode.PONG, frame.payload, 10.0)
            return None
        if frame.opcode == Opcode.PONG:
            return None
        if frame.opcode == Opcode.CLOSE:
            code, reason = _close_payload(frame.payload)
            self._answer_close(Close.NORMAL if code == Close.NO_STATUS else code)
            self._closed = ClosedError(code, reason, by_peer=True)
            raise self._closed
        if frame.opcode == Opcode.CONTINUATION:
            if self._kind is None:
                raise _ViolationError(Close.PROTOCOL_ERROR, "a continuation of nothing")
        elif self._kind is not None:
            raise _ViolationError(Close.PROTOCOL_ERROR, "a new message mid-fragment")
        else:
            self._kind = frame.opcode
        self._parts.append(frame.payload)
        if sum(len(part) for part in self._parts) > self._max:
            raise _ViolationError(Close.TOO_BIG, "fragments past the message bound")
        if not frame.fin:
            return None
        data, kind = b"".join(self._parts), self._kind
        self._parts, self._kind = [], None
        if kind == Opcode.BINARY:
            return data
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _ViolationError(Close.INVALID_DATA, "text that is not UTF-8") from exc

    # -- closing --

    def _answer_close(self, code: int) -> None:
        try:
            self._sock.settimeout(CLOSE_WAIT_S)
            self._sock.sendall(
                encode_frame(Opcode.CLOSE, struct.pack("!H", code), os.urandom(4))
            )
        except OSError:
            pass
        self._shut()

    def _fail(self, code: Close, why: str) -> None:
        """Close for a server frame the RFC forbids."""
        self._answer_close(code)
        self._closed = ClosedError(code, why, by_peer=False)

    def _drop(self, code: Close, why: str) -> None:
        self._shut()
        self._closed = ClosedError(code, why, by_peer=False)

    def _shut(self) -> None:
        with contextlib.suppress(OSError):
            self._sock.close()

    def close(self, code: int = Close.NORMAL, reason: str = "") -> None:
        """Close the channel: send the close, wait briefly for the server's."""
        if self._closed is not None:
            return
        payload = struct.pack("!H", code) + reason.encode("utf-8")[: _MAX_CONTROL - 2]
        try:
            self._sock.settimeout(CLOSE_WAIT_S)
            self._sock.sendall(encode_frame(Opcode.CLOSE, payload, os.urandom(4)))
            deadline = time.monotonic() + CLOSE_WAIT_S
            while time.monotonic() < deadline:
                frame = self._next_frame(deadline)
                if frame is None or frame.opcode == Opcode.CLOSE:
                    break
        except (OSError, WebSocketError, _ViolationError):
            pass
        self._shut()
        self._closed = ClosedError(code, reason, by_peer=False)


def _read_answer(sock: socket.socket, deadline: float) -> tuple[bytes, bytes]:
    data = b""
    while b"\r\n\r\n" not in data:
        if len(data) > MAX_HANDSHAKE_BYTES:
            raise HandshakeError("the server's answer is past its bound")
        left = deadline - time.monotonic()
        if left <= 0:
            raise HandshakeError("the server did not answer in time")
        sock.settimeout(left)
        try:
            chunk = sock.recv(4096)
        except TimeoutError as exc:
            raise HandshakeError("the server did not answer in time") from exc
        if not chunk:
            raise HandshakeError("the server closed the connection")
        data += chunk
    head, _, rest = data.partition(b"\r\n\r\n")
    if len(head) > MAX_HANDSHAKE_BYTES:
        raise HandshakeError("the server's answer is past its bound")
    return head, rest


def _check_answer(head: bytes, key: str) -> None:
    lines = head.decode("latin-1").split("\r\n")
    status = re.fullmatch(r"HTTP/1\.1 ([0-9]{3})(?: .*)?", lines[0])
    if status is None:
        raise HandshakeError("the server did not answer in HTTP")
    code = int(status.group(1))
    if code != 101:
        raise HandshakeError(f"the server answered HTTP {code}", status=code)
    headers: dict[str, str] = {}
    for line in lines[1:]:
        name, colon, value = line.partition(":")
        if not colon:
            raise HandshakeError("the server's answer has a malformed header", 101)
        headers[name.strip().lower()] = value.strip()
    if headers.get("upgrade", "").lower() != "websocket":
        raise HandshakeError("the server did not upgrade to websocket", 101)
    tokens = {t.strip().lower() for t in headers.get("connection", "").split(",")}
    if "upgrade" not in tokens:
        raise HandshakeError("the server did not upgrade the connection", 101)
    if headers.get("sec-websocket-accept") != accept_key(key):
        raise HandshakeError("the server's accept key is wrong", 101)
    for asked_for_none in ("sec-websocket-extensions", "sec-websocket-protocol"):
        if asked_for_none in headers:
            raise HandshakeError(
                f"the server chose a {asked_for_none} not asked for", 101
            )


def connect(
    url: str,
    *,
    headers: Mapping[str, str],
    timeout: float,
    max_message: int,
    ssl_context: ssl.SSLContext | None = None,
) -> WebSocket:
    """Open a websocket to ``url``, sending ``headers`` with the upgrade.

    ``timeout`` bounds the connect, the TLS handshake and the upgrade
    together. :class:`HandshakeError` when the server is not reached or does
    not switch; ``ValueError`` for a URL or header that cannot be sent.
    """
    target = parse_url(url)
    for name, value in headers.items():
        if not _TOKEN.fullmatch(name) or not _VALUE.fullmatch(value):
            raise ValueError(f"the header {name!r} cannot be sent as it is")
    deadline = time.monotonic() + timeout
    try:
        raw = socket.create_connection((target.host, target.port), timeout=timeout)
    except OSError as exc:
        raise HandshakeError(f"cannot reach the server: {exc.strerror or exc}") from exc
    sock: socket.socket = raw
    try:
        if target.secure:
            context = ssl_context or default_ssl_context()
            sock.settimeout(max(deadline - time.monotonic(), 0.001))
            sock = context.wrap_socket(raw, server_hostname=target.host)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        lines = [
            f"GET {target.path} HTTP/1.1",
            f"Host: {target.authority}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
            *(f"{name}: {value}" for name, value in headers.items()),
        ]
        sock.settimeout(max(deadline - time.monotonic(), 0.001))
        sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))
        head, rest = _read_answer(sock, deadline)
        _check_answer(head, key)
    except HandshakeError:
        sock.close()
        raise
    except (OSError, ssl.SSLError) as exc:
        sock.close()
        raise HandshakeError(f"the handshake failed: {exc.__class__.__name__}") from exc
    return WebSocket(sock, max_message=max_message, buffer=rest)
