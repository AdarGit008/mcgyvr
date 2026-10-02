"""The hub's UDP formats as a rig speaks them: binding requests, probes, relay binds.

The hub's protocol schema states these formats (its ``x-udp`` block, and the
layouts in the hub's protocol module); the tests hold every constant here to
the pinned copy. All are big-endian, and a request is never smaller than its
answer, so nothing here is an amplifier::

    binding request  "MCGS" 01 01 0000 token[16] txid[12] zeros  (64-512 bytes)
    binding answer   "MCGS" 01 02 family(04|06) 00 txid[12] port[2] address
    probe packet     "MCGP" 01 kind 0000 secret[16] seq[4] stamp[8] padding
                     (36-1200 bytes; kind 1 ping, 2 pong — the ping echoed,
                     same length — 3 bulk)
    relay bind       "MCGR" 01 01 length[2] ticket zeros  (96-512 bytes)
    relay answer     "MCGR" 01 02 port[2]  |  "MCGR" 01 03 reason[1]

Everything read here comes off the network, so every reader takes bytes of
any length and returns ``None`` for anything that is not exactly its format:
the caller drops it without an answer.

This file imports nothing of the product's, only the standard library: the
tunnel container runs it as it is (``python3 -c <this file> stun …``) to
send its binding requests from the WireGuard port itself, so the address the
hub sees is the one WireGuard's packets will leave by (:func:`main`).
"""

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

#: The formats' version byte.
VERSION = 1
STUN_MAGIC = b"MCGS"
PROBE_MAGIC = b"MCGP"
RELAY_MAGIC = b"MCGR"
#: The bounds the formats state, in bytes.
STUN_REQUEST_MIN_BYTES = 64
STUN_REQUEST_MAX_BYTES = 512
PROBE_PACKET_MIN_BYTES = 36
PROBE_PACKET_MAX_BYTES = 1200
RELAY_BIND_MIN_BYTES = 96
RELAY_BIND_MAX_BYTES = 512
RELAY_MAX_PACKET_BYTES = 2048
TOKEN_BYTES = 16
TXID_BYTES = 12
#: The kinds of a probe packet.
PING = 1
PONG = 2
BULK = 3
#: A relay ticket, as the hub's schema shapes it.
TICKET = re.compile(r"[A-Za-z0-9_-]{22,256}")
#: The largest datagram any reader here is handed: a full UDP payload, so a
#: datagram over a format's bound is seen whole and refused, never cut.
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
#: The largest sequence number and stamp the probe format carries.
MAX_SEQ = (1 << 32) - 1
MAX_STAMP = (1 << 64) - 1


@dataclass(frozen=True, kw_only=True)
class BindingAnswer:
    """What the hub's responder saw: the request's source, by transaction."""

    txid: bytes
    host: str
    port: int


@dataclass(frozen=True, kw_only=True)
class Probe:
    """One probe packet, read."""

    kind: int
    secret: bytes
    seq: int
    stamp: int
    size: int


@dataclass(frozen=True, kw_only=True)
class RelayRefused:
    """The relay would not bind; ``reason`` is its code."""

    reason: int


def _pad(head: bytes, size: int, low: int, high: int) -> bytes:
    if not max(low, len(head)) <= size <= high:
        raise ValueError(f"size: not {max(low, len(head))} to {high} bytes")
    return head + bytes(size - len(head))


def binding_request(
    token: bytes, txid: bytes, *, size: int = STUN_REQUEST_MIN_BYTES
) -> bytes:
    """A binding request carrying ``token``, as transaction ``txid``."""
    if len(token) != TOKEN_BYTES or len(txid) != TXID_BYTES:
        raise ValueError("token and txid: not of their lengths")
    head = _STUN_HEAD.pack(STUN_MAGIC, VERSION, _REQUEST, 0, token, txid)
    return _pad(head, size, STUN_REQUEST_MIN_BYTES, STUN_REQUEST_MAX_BYTES)


def read_binding_answer(data: bytes) -> BindingAnswer | None:
    """The binding answer ``data`` is, or ``None``."""
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
    """A probe packet of ``kind`` between the pair ``secret`` names."""
    if kind not in (PING, PONG, BULK) or len(secret) != TOKEN_BYTES:
        raise ValueError("kind and secret: not a probe's")
    if not (0 <= seq <= MAX_SEQ and 0 <= stamp <= MAX_STAMP):
        raise ValueError("seq and stamp: out of their bounds")
    head = _PROBE_HEAD.pack(PROBE_MAGIC, VERSION, kind, 0, secret, seq, stamp)
    return _pad(head, size, PROBE_PACKET_MIN_BYTES, PROBE_PACKET_MAX_BYTES)


def read_probe(data: bytes) -> Probe | None:
    """The probe packet ``data`` is, or ``None``."""
    if not PROBE_PACKET_MIN_BYTES <= len(data) <= PROBE_PACKET_MAX_BYTES:
        return None
    magic, version, kind, _, secret, seq, stamp = _PROBE_HEAD.unpack_from(data)
    if (magic, version) != (PROBE_MAGIC, VERSION) or kind not in (PING, PONG, BULK):
        return None
    return Probe(kind=kind, secret=secret, seq=seq, stamp=stamp, size=len(data))


def pong(ping: bytes) -> bytes | None:
    """The answer to a ping: the same bytes, the same length, kind pong."""
    read = read_probe(ping)
    if read is None or read.kind != PING:
        return None
    return ping[:5] + bytes([PONG]) + ping[6:]


def relay_bind(ticket: str, *, size: int | None = None) -> bytes:
    """A relay bind carrying ``ticket``: the format's least size, or the
    ticket's own when longer, unless ``size`` says."""
    if not TICKET.fullmatch(ticket):
        raise ValueError("ticket: not of its shape")
    raw = ticket.encode("ascii")
    head = _RELAY_HEAD.pack(RELAY_MAGIC, VERSION, _REQUEST, len(raw)) + raw
    wanted = max(RELAY_BIND_MIN_BYTES, len(head)) if size is None else size
    return _pad(head, wanted, RELAY_BIND_MIN_BYTES, RELAY_BIND_MAX_BYTES)


def read_relay_answer(data: bytes) -> int | RelayRefused | None:
    """The port the relay bound this rig's side to, its refusal, or ``None``."""
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
    """Send binding requests from ``sock`` to each server, ``attempts`` rounds
    ``wait_s`` apart; the first round trip (in microseconds) and answer of
    each server that answered. Only an answer from the server asked, to a
    transaction this call sent, is taken."""
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


def _servers(words: Sequence[str]) -> list[tuple[str, int]]:
    servers = []
    for host, port in zip(words[::2], words[1::2], strict=True):
        servers.append((str(ipaddress.IPv4Address(host)), int(port)))
    return servers


def main(argv: Sequence[str]) -> int:
    """The tunnel container's helper, run before WireGuard takes its port:

    * ``stun PORT TOKEN ATTEMPTS WAIT_MS HOST SPORT [HOST SPORT]`` sends
      binding requests from ``PORT`` and prints ``rtt HOST SPORT US`` for
      each server that answered;
    * ``keep PORT TOKEN EVERY_S LIFETIME_S PIDFILE HOST SPORT [HOST SPORT]``
      sends one request to each server every ``EVERY_S`` from ``PORT``, so
      the address the hub saw stays the port's, until ``LIFETIME_S`` is up or
      it is ended (its pid is in ``PIDFILE``); answers are read and dropped.
    """
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
