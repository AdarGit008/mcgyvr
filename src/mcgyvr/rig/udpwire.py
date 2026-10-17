""

from __future__ import annotations

import ipaddress
import os
import re
import secrets
import signal
import socket
import struct
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass

#
VERSION = 1
STUN_MAGIC = b"MCGS"
PROBE_MAGIC = b"MCGP"
RELAY_MAGIC = b"MCGR"
#
STUN_REQUEST_MIN_BYTES = 64
STUN_REQUEST_MAX_BYTES = 512
PROBE_PACKET_MIN_BYTES = 36
PROBE_PACKET_MAX_BYTES = 1200
RELAY_BIND_MIN_BYTES = 96
RELAY_BIND_MAX_BYTES = 512
RELAY_MAX_PACKET_BYTES = 2048
TOKEN_BYTES = 16
TXID_BYTES = 12
#
PING = 1
PONG = 2
BULK = 3
#
BAD_TICKET = 1
EXPIRED = 2
FULL = 3
RATE_LIMITED = 4
#
TICKET = re.compile(r"[A-Za-z0-9_-]{22,256}")
#
#
RECEIVE_BYTES = 65535

_REQUEST = 1
_ANSWER = 2
_REFUSED = 3
_STUN_HEAD = struct.Struct(f"!4sBBH{TOKEN_BYTES}s{TXID_BYTES}s")
_STUN_ANSWER = struct.Struct(f"!4sBBBx{TXID_BYTES}sH")
_PROBE_HEAD = struct.Struct(f"!4sBBH{TOKEN_BYTES}sIQ")
_RELAY_HEAD = struct.Struct("!4sBBH")
_RELAY_REFUSED = struct.Struct("!4sBBB")
_FAMILIES = {4: 4, 6: 16}
#
#
STUN_ATTEMPTS = 3
#
MAX_SEQ = (1 << 32) - 1
MAX_STAMP = (1 << 64) - 1


@dataclass(frozen=True, kw_only=True)
class BindingAnswer:
    ""

    txid: bytes
    host: str
    port: int


@dataclass(frozen=True, kw_only=True)
class Probe:
    ""

    kind: int
    secret: bytes
    seq: int
    stamp: int
    size: int


@dataclass(frozen=True, kw_only=True)
class RelayRefused:
    ""

    reason: int


def _pad(head: bytes, size: int, low: int, high: int) -> bytes:
    if not max(low, len(head)) <= size <= high:
        raise ValueError(f"size: not {max(low, len(head))} to {high} bytes")
    return head + bytes(size - len(head))


def binding_request(
    token: bytes, txid: bytes, *, size: int = STUN_REQUEST_MIN_BYTES
) -> bytes:
    ""
    if len(token) != TOKEN_BYTES or len(txid) != TXID_BYTES:
        raise ValueError("token and txid: not of their lengths")
    head = _STUN_HEAD.pack(STUN_MAGIC, VERSION, _REQUEST, 0, token, txid)
    return _pad(head, size, STUN_REQUEST_MIN_BYTES, STUN_REQUEST_MAX_BYTES)


def read_binding_answer(data: bytes) -> BindingAnswer | None:
    ""
    if len(data) < _STUN_ANSWER.size:
        return None
    magic, version, kind, family, txid, port = _STUN_ANSWER.unpack_from(data)
    rest = data[_STUN_ANSWER.size :]
    if (magic, version, kind) != (STUN_MAGIC, VERSION, _ANSWER):
        return None
    if _FAMILIES.get(family) != len(rest) or port == 0:
        return None
    return BindingAnswer(txid=txid, host=str(ipaddress.ip_address(rest)), port=port)


def probe_packet(
    kind: int,
    secret: bytes,
    seq: int,
    stamp: int,
    *,
    size: int = PROBE_PACKET_MIN_BYTES,
) -> bytes:
    ""
    if kind not in (PING, PONG, BULK) or len(secret) != TOKEN_BYTES:
        raise ValueError("kind and secret: not a probe's")
    if not (0 <= seq <= MAX_SEQ and 0 <= stamp <= MAX_STAMP):
        raise ValueError("seq and stamp: out of their bounds")
    head = _PROBE_HEAD.pack(PROBE_MAGIC, VERSION, kind, 0, secret, seq, stamp)
    return _pad(head, size, PROBE_PACKET_MIN_BYTES, PROBE_PACKET_MAX_BYTES)


def read_probe(data: bytes) -> Probe | None:
    ""
    if not PROBE_PACKET_MIN_BYTES <= len(data) <= PROBE_PACKET_MAX_BYTES:
        return None
    magic, version, kind, _, secret, seq, stamp = _PROBE_HEAD.unpack_from(data)
    if (magic, version) != (PROBE_MAGIC, VERSION) or kind not in (PING, PONG, BULK):
        return None
    return Probe(kind=kind, secret=secret, seq=seq, stamp=stamp, size=len(data))


def pong(ping: bytes) -> bytes | None:
    ""
    read = read_probe(ping)
    if read is None or read.kind != PING:
        return None
    return ping[:5] + bytes([PONG]) + ping[6:]


def relay_bind(ticket: str, *, size: int | None = None) -> bytes:
    ""
    if not TICKET.fullmatch(ticket):
        raise ValueError("ticket: not of its shape")
    raw = ticket.encode("ascii")
    head = _RELAY_HEAD.pack(RELAY_MAGIC, VERSION, _REQUEST, len(raw)) + raw
    wanted = max(RELAY_BIND_MIN_BYTES, len(head)) if size is None else size
    return _pad(head, wanted, RELAY_BIND_MIN_BYTES, RELAY_BIND_MAX_BYTES)


def read_relay_answer(data: bytes) -> int | RelayRefused | None:
    ""
    if len(data) == _RELAY_HEAD.size:
        magic, version, kind, port = _RELAY_HEAD.unpack(data)
        if (magic, version, kind) == (RELAY_MAGIC, VERSION, _ANSWER) and port:
            return int(port)
        return None
    if len(data) == _RELAY_REFUSED.size:
        magic, version, kind, reason = _RELAY_REFUSED.unpack(data)
        if (magic, version, kind) == (RELAY_MAGIC, VERSION, _REFUSED):
            return RelayRefused(reason=reason)
    return None


def _now_us() -> int:
    return time.monotonic_ns() // 1000


def ask_bindings(
    sock: socket.socket,
    token: bytes,
    servers: Sequence[tuple[str, int]],
    *,
    attempts: int,
    wait_s: float,
) -> dict[tuple[str, int], tuple[int, BindingAnswer]]:
    ""
    sent: dict[bytes, tuple[tuple[str, int], int]] = {}
    found: dict[tuple[str, int], tuple[int, BindingAnswer]] = {}
    for _ in range(attempts):
        for server in servers:
            if server in found:
                continue
            txid = secrets.token_bytes(TXID_BYTES)
            sent[txid] = (server, _now_us())
            sock.sendto(binding_request(token, txid), server)
        deadline = time.monotonic() + wait_s
        while len(found) < len(servers):
            left = deadline - time.monotonic()
            if left <= 0:
                break
            sock.settimeout(left)
            try:
                data, source = sock.recvfrom(RECEIVE_BYTES)
            except TimeoutError:
                break
            answer = read_binding_answer(data)
            if answer is None or answer.txid not in sent:
                continue
            server, at = sent[answer.txid]
            if (source[0], source[1]) != server or server in found:
                continue
            found[server] = (_now_us() - at, answer)
        if len(found) == len(servers):
            break
    return found


def bind_relay(
    host: str, port: int, ticket: str, *, attempts: int = 3, wait_s: float = 1.0
) -> int | RelayRefused | None:
    ""
    packet = relay_bind(ticket)
    target = (host, port)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        for _ in range(attempts):
            sock.sendto(packet, target)
            deadline = time.monotonic() + wait_s
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                sock.settimeout(left)
                try:
                    data, source = sock.recvfrom(RECEIVE_BYTES)
                except TimeoutError:
                    break
                if (source[0], source[1]) != target:
                    continue
                answer = read_relay_answer(data)
                if answer is not None:
                    return answer
    return None


def _servers(words: Sequence[str]) -> list[tuple[str, int]]:
    servers = []
    for host, port in zip(words[::2], words[1::2], strict=True):
        servers.append((str(ipaddress.IPv4Address(host)), int(port)))
    return servers


def main(argv: Sequence[str]) -> int:
    ""
    if len(argv) < 7 or argv[0] not in ("stun", "keep"):
        print("usage: stun|keep …", file=sys.stderr)
        return 2
    command, port, token = argv[0], int(argv[1]), bytes.fromhex(argv[2])
    if len(token) != TOKEN_BYTES:
        print("token: not 16 bytes", file=sys.stderr)
        return 2
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("0.0.0.0", port))
        if command == "stun":
            servers = _servers(argv[5:])
            found = ask_bindings(
                sock,
                token,
                servers,
                attempts=int(argv[3]),
                wait_s=int(argv[4]) / 1000,
            )
            for (host, sport), (rtt_us, _) in found.items():
                print(f"rtt {host} {sport} {rtt_us}", flush=True)
            return 0
        every_s, lifetime_s = float(argv[3]), float(argv[4])
        servers = _servers(argv[6:])
        with open(argv[5], "w", encoding="ascii") as handle:
            handle.write(f"{os.getpid()}\n")
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        sock.setblocking(False)
        end = time.monotonic() + lifetime_s
        while time.monotonic() < end:
            for server in servers:
                txid = secrets.token_bytes(TXID_BYTES)
                sock.sendto(binding_request(token, txid), server)
            time.sleep(every_s)
            while True:
                try:
                    sock.recvfrom(RECEIVE_BYTES)
                except BlockingIOError:
                    break
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
