"""A websocket client: the opening handshake and the frame protocol, by hand.

It reads a ``ws://`` or ``wss://`` URL, connects over a plain or TLS socket,
writes the HTTP upgrade request itself and checks the server's answer down to
the accept key. After that the connection carries frames: text goes out as one
masked frame, and a frame from the server is checked for shape and assembled
across fragments into a ``str`` for text or ``bytes`` for binary. A ping is
answered, a close from the peer is answered and reported, and a peer that
breaks the framing rules is closed with the code the rules name. Every read is
bounded by a deadline and every message by a byte limit, and a receive waiting
on a frame can be cut short from another thread.
"""

from __future__ import annotations

import base64
import contextlib
import enum
import hashlib
import os
import re
import selectors
import socket
import ssl
import struct
import time
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass

#: The longest the server's answer to the upgrade may run to, in bytes, before it is
#: refused as too long
MAX_HANDSHAKE_BYTES = 16 * 1024
#: The GUID the protocol appends to a client key before hashing it into the answer
_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
#: The most bytes a control frame's payload may hold
_MAX_CONTROL = 125
#: The seconds a close may spend: writing the frame, then waiting for the peer's
CLOSE_WAIT_S = 1.0

#: The token characters a header name must be, and the field-value characters a header
#: value and a whole URL must be, or the request cannot carry either
_TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
_VALUE = re.compile(r"[\t\x20-\x7e]*")


class Opcode(enum.IntEnum):
    """Every frame opcode the protocol defines; anything else is a protocol error."""

    CONTINUATION = 0
    TEXT = 1
    BINARY = 2
    CLOSE = 8
    PING = 9
    PONG = 10


class Close(enum.IntEnum):
    """The close codes this client sends, and the two it only ever reports."""

    NORMAL = 1000
    PROTOCOL_ERROR = 1002
    INVALID_DATA = 1007
    TOO_BIG = 1009
    #: Never sent: reported for a close from the peer that carried no status code
    NO_STATUS = 1005
    #: Never sent: reported for a connection that dropped before any close frame
    ABNORMAL = 1006


class WebSocketError(Exception):
    """Base of what this client raises when it cannot connect or the link fails."""


class HandshakeError(WebSocketError):
    """The opening handshake failed.

    ``status`` is the HTTP status the server answered with, or ``None`` when the
    answer was never readable as an HTTP response at all.
    """

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ClosedError(WebSocketError):
    """The connection is closed, whatever closed it.

    ``code`` and ``reason`` are what the close frame carried, and ``by_peer`` says
    whether the peer closed it or this side did.
    """

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
    """A websocket URL, read into the four things the request needs to be sent."""

    secure: bool
    host: str
    port: int
    path: str

    @property
    def authority(self) -> str:
        """The ``Host`` header value for this target.

        The host in brackets when it is an IPv6 literal, and the port only when it
        is not the scheme's default.
        """
        host = f"[{self.host}]" if ":" in self.host else self.host
        default = 443 if self.secure else 80
        return host if self.port == default else f"{host}:{self.port}"


def parse_url(url: str) -> Target:
    """Read a ``ws://`` or ``wss://`` URL into the ``Target`` it names.

    A ``ValueError`` refuses what a request line or a ``Host`` header cannot carry:
    whitespace or another character outside the ASCII a request allows, credentials
    in the URL, a fragment, no host at all, or a port outside 1 to 65535.
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
    """The TLS context a ``wss://`` connect builds when the caller passes none.

    The system default, so the certificate is verified, with TLS 1.2 as its floor.
    """
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def accept_key(key: str) -> str:
    """The ``Sec-WebSocket-Accept`` value the server has to answer a client key with.

    The base64 of the SHA-1 of the key with the protocol's GUID appended.
    """
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
    """One final, masked client frame: header, the four-byte key, then the payload.

    The header states the opcode and the payload's length in two, four or ten bytes
    depending on how long it is, and the payload is XORed with ``key``.
    """
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
    """Cut one frame off the front of ``buffer``, if it holds a whole one.

    Returns the frame and how many bytes of the buffer it used, or ``None`` when
    more bytes are needed. ``limit`` is the most a data frame's payload may be; a
    frame that breaks the framing rules raises ``_ViolationError`` carrying the
    close code to answer with.
    """
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
    """One open connection: frames out, messages in, a close handshake at either end.

    ``send_text`` writes one masked frame, ``receive`` returns the next whole message
    or ``None`` when its time is up, and the connection ends on a close from the
    peer, a protocol violation, a dropped socket or a ``close`` of this side's. Once
    it has ended, later calls raise the same ``ClosedError``.
    """

    def __init__(self, sock: socket.socket, *, max_message: int, buffer: bytes) -> None:
        self._sock = sock
        self._max = max_message
        self._buffer = bytearray(buffer)
        self._parts: list[bytes] = []
        self._kind: int | None = None
        self._closed: ClosedError | None = None
        # The selector watches the socket for frames and the read end of this pair for
        # a wake, which is how a waiting receive is cut short from another thread.
        self._woken, self._waker = socket.socketpair()
        self._woken.setblocking(False)
        self._waker.setblocking(False)
        self._selector = selectors.DefaultSelector()
        self._selector.register(self._sock, selectors.EVENT_READ)
        self._selector.register(self._woken, selectors.EVENT_READ)

    def wake(self) -> None:
        """Cut a ``receive`` in another thread short, so it returns ``None``."""
        # Already shut means nobody waits, so a send that fails here is not an error
        with contextlib.suppress(OSError):
            self._waker.send(b"\0")

    # A send is one complete masked frame, and a write that fails drops the connection

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
        """Send ``text`` as one masked text frame.

        A message past the connection's bound is a ``ValueError`` raised before
        anything is written. ``timeout`` bounds the write.
        """
        payload = text.encode("utf-8")
        if len(payload) > self._max:
            raise ValueError(f"a message of {len(payload)} bytes is past the bound")
        self._send(Opcode.TEXT, payload, timeout)

    # A read returns one whole message: a control frame is answered or ignored, and a
    # fragment is held until the frame that ends the message arrives

    def receive(self, timeout: float) -> str | bytes | None:
        """Wait up to ``timeout`` seconds for the next whole message.

        ``str`` for a text message, ``bytes`` for a binary one, and ``None`` if the
        deadline, or a ``wake`` from another thread, came first. Along the way a ping
        is answered, a pong dropped and a fragment held until its last part arrives;
        a close or a protocol violation raises ``ClosedError``.
        """
        deadline = time.monotonic() + timeout
        while True:
            if self._closed is not None:
                raise self._closed
            try:
                frame = self._next_frame(deadline, wakeable=True)
                if frame is None:
                    return None
                message = self._take(frame)
            except _ViolationError as violation:
                self._fail(violation.code, violation.why)
                continue
            if message is not None:
                return message

    def _next_frame(self, deadline: float, *, wakeable: bool = False) -> _Frame | None:
        while True:
            parsed = _parse_frame(self._buffer, self._max)
            if parsed is not None:
                frame, used = parsed
                del self._buffer[:used]
                return frame
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            if wakeable and not self._readable(left):
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

    def _readable(self, left: float) -> bool:
        """Whether a frame or the end of the connection is ready within ``left``.

        Waits up to ``left`` seconds in the selector. A wake counts as ready and
        returns ``False``, so the ``receive`` waiting on it gives up instead of
        reading.
        """
        if isinstance(self._sock, ssl.SSLSocket) and self._sock.pending():
            return True  # Data already decrypted is waiting inside the TLS layer
        ready = {key.fileobj for key, _ in self._selector.select(left)}
        if self._woken in ready:
            with contextlib.suppress(OSError):  # Drain the wake byte
                while self._woken.recv(4096):
                    pass
            return False
        return self._sock in ready

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

    # A close, from either side, is a frame written out and then the sockets shut

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
        """Close on a protocol violation, remembering ``why``.

        The frame carrying ``code`` is sent, the sockets are shut, and the failure is
        recorded so the caller's next check raises it.
        """
        self._answer_close(code)
        self._closed = ClosedError(code, why, by_peer=False)

    def _drop(self, code: Close, why: str) -> None:
        self._shut()
        self._closed = ClosedError(code, why, by_peer=False)

    def _shut(self) -> None:
        with contextlib.suppress(OSError):
            self._selector.close()
        for sock in (self._sock, self._woken, self._waker):
            with contextlib.suppress(OSError):
                sock.close()

    def close(self, code: int = Close.NORMAL, reason: str = "") -> None:
        """Close from this side, saying ``code`` and as much of ``reason`` as fits.

        The close frame goes out, then frames are read for the close window until the
        peer's close arrives or the window runs out, and the sockets are shut. A
        connection that is already closed is left as it is.
        """
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
    """Connect to ``url``, returning the ``WebSocket`` once the answer checks out.

    The headers are checked before anything is dialled, then the socket is opened
    (wrapped for ``wss://``), the upgrade request is written and the answer is
    checked, a subprotocol or extension never asked for being a refusal. ``timeout``
    bounds the whole exchange, and the connection keeps whatever bytes arrived after
    the answer.
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
