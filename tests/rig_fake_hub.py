"""A websocket server for the rig agent's tests, on this machine only.

:class:`Server` listens on ``127.0.0.1`` on a port the system picks and hands
each connection it accepts, in a thread of its own, to a script: a function
that takes a :class:`Peer` and plays the hub's side, frame by frame, including
frames no honest server sends. Nothing here is the hub; it is the wire as RFC
6455 lays it out, so a test can say exactly what arrives and in what pieces.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import socket
import struct
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

TEXT, BINARY, CLOSE, PING, PONG, CONTINUATION = 1, 2, 8, 9, 10, 0


@dataclass
class Frame:
    fin: bool
    opcode: int
    payload: bytes
    masked: bool


@dataclass
class Peer:
    """The server's end of one connection."""

    sock: socket.socket
    request: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    _buffer: bytes = b""

    def read_request(self) -> None:
        while b"\r\n\r\n" not in self._buffer:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("client left before its request")
            self._buffer += chunk
        head, _, self._buffer = self._buffer.partition(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        self.request = lines[0]
        for line in lines[1:]:
            name, _, value = line.partition(":")
            self.headers[name.strip().lower()] = value.strip()

    def accept_key(self) -> str:
        key = self.headers["sec-websocket-key"]
        digest = hashlib.sha1((key + GUID).encode()).digest()
        return base64.b64encode(digest).decode()

    def handshake(
        self,
        status: str = "101 Switching Protocols",
        accept: str | None = None,
        extra: str = "",
    ) -> None:
        """Read the request and answer it; an honest 101 by default."""
        self.read_request()
        if not status.startswith("101"):
            self.send_raw(f"HTTP/1.1 {status}\r\nContent-Length: 0\r\n\r\n".encode())
            return
        self.send_raw(
            (
                f"HTTP/1.1 {status}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept or self.accept_key()}\r\n"
                f"{extra}\r\n"
            ).encode()
        )

    def send_raw(self, data: bytes) -> None:
        self.sock.sendall(data)

    def send_frame(
        self,
        opcode: int,
        payload: bytes = b"",
        *,
        fin: bool = True,
        rsv: int = 0,
        mask: bool = False,
        length: int | None = None,
    ) -> None:
        """One frame as a server writes it, or as a hostile one would."""
        first = (0x80 if fin else 0) | (rsv << 4) | opcode
        n = len(payload) if length is None else length
        if n < 126:
            head = struct.pack("!BB", first, (0x80 if mask else 0) | n)
        elif n < 1 << 16:
            head = struct.pack("!BBH", first, (0x80 if mask else 0) | 126, n)
        else:
            head = struct.pack("!BBQ", first, (0x80 if mask else 0) | 127, n)
        if mask:
            key = b"\x01\x02\x03\x04"
            payload = bytes(b ^ key[i % 4] for i, b in enumerate(payload))
            head += key
        self.send_raw(head + payload)

    def send_text(self, text: str) -> None:
        self.send_frame(TEXT, text.encode())

    def send_close(self, code: int, reason: str = "") -> None:
        self.send_frame(CLOSE, struct.pack("!H", code) + reason.encode())

    def _fill(self, n: int) -> bytes:
        while len(self._buffer) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("client left mid-frame")
            self._buffer += chunk
        data, self._buffer = self._buffer[:n], self._buffer[n:]
        return data

    def recv_frame(self) -> Frame:
        """The client's next frame, unmasked."""
        first, second = self._fill(2)
        n = second & 0x7F
        if n == 126:
            (n,) = struct.unpack("!H", self._fill(2))
        elif n == 127:
            (n,) = struct.unpack("!Q", self._fill(8))
        masked = bool(second & 0x80)
        key = self._fill(4) if masked else b"\0\0\0\0"
        payload = bytes(b ^ key[i % 4] for i, b in enumerate(self._fill(n)))
        return Frame(
            fin=bool(first & 0x80), opcode=first & 0x0F, payload=payload, masked=masked
        )

    def recv_text(self) -> str:
        """The client's next data frame as text, answering nothing on the way."""
        frame = self.recv_frame()
        assert frame.opcode == TEXT, frame
        return frame.payload.decode()


Script = Callable[[Peer], None]


class Server:
    """Accepts connections on 127.0.0.1 and plays one script for each, in turn.

    ``scripts`` are played in order, one per accepted connection; a connection
    beyond them is closed at once. An exception a script raises is kept in
    :attr:`failures` for the test to assert on.
    """

    def __init__(self, *scripts: Script) -> None:
        self.scripts = list(scripts)
        self.peers: list[Peer] = []
        self.failures: list[BaseException] = []
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(8)
        self._listener.settimeout(0.05)
        self.port: int = self._listener.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._stopped = threading.Event()

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}/api/v1/agent"

    def __enter__(self) -> Server:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stopped.set()
        self._thread.join(timeout=15)
        self._listener.close()

    def _serve(self) -> None:
        index = 0
        while not self._stopped.is_set():
            try:
                sock, _ = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            sock.settimeout(10)
            if index >= len(self.scripts):
                sock.close()
                continue
            peer = Peer(sock)
            self.peers.append(peer)
            script = self.scripts[index]
            index += 1
            try:
                script(peer)
            except BaseException as exc:  # kept for the test, never swallowed
                self.failures.append(exc)
            finally:
                with contextlib.suppress(OSError):
                    sock.close()
