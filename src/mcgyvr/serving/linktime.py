#!/usr/bin/env python3
# Standalone link timer: it measures a single hop of a machine's data path
# (two GPUs, or two machines over TCP) and prints the readings as JSON.
"""Time one link of a machine's data path and report the readings as JSON.

The command line is ``mcgyvr-linktime MODE A B``, where MODE picks the seam:

``peer CARD_A CARD_B`` copies between two local GPUs with ``cuMemcpyPeer``,
``sink ADDRESS PORT`` receives length-prefixed TCP messages and acknowledges
each one, and ``send ADDRESS PORT`` times messages pushed at a ``sink``.

A run prints its readings on stdout, or ``{"error": ...}`` and a non-zero exit
status when anything fails.
"""

from __future__ import annotations

import contextlib
import ctypes
import ipaddress
import json
import os
import socket
import struct
import sys
import time
from typing import Any

# Command word and mode names main() insists on before doing any work.
LINK_WORD = "mcgyvr-linktime"
# Accepted modes, also joined into the usage message main() raises.
MODES = ("peer", "sink", "send")
# Default TCP port for the sink and send modes. main() takes the port from
# argv, so this is the value callers are expected to pass on both ends.
LINK_PORT = 50151

# Copy sizes in bytes for the peer mode (64 KiB, 1 MiB, 8 MiB); each is timed
# REPEATS times, after one untimed warm-up copy of the smallest size.
PEER_PAYLOADS = (1 << 16, 1 << 20, 1 << 23)
# Message sizes in bytes for the send and sink modes (4 KiB, 256 KiB, 4 MiB).
NETWORK_PAYLOADS = (1 << 12, 1 << 18, 1 << 22)
# Timed messages per payload size, in every mode.
REPEATS = 3
# Free memory each card must still hold once the peer mode has allocated its
# largest buffer, so the timer never leaves a GPU at the edge of its memory.
HEADROOM_BYTES = 256 << 20
# Most payload the sink will accept over one connection: one warm-up message
# plus REPEATS timed messages of every network payload, plus a little slack.
SINK_MOST_BYTES = (sum(NETWORK_PAYLOADS) * (REPEATS + 1)) + 64
# Handshake bounds in seconds: how long the sink waits for its one client to
# connect, and how long the sender keeps retrying a failed connect.
ACCEPT_S = 60.0
CONNECT_S = 30.0
# Per-call socket timeout, so a silent peer fails instead of hanging.
IDLE_S = 15.0
# Wall-clock bound on a whole run; running past it is reported as an error.
WHOLE_S = 120.0

# Big-endian 8-byte length prefix on every message; a length of zero ends the
# exchange.
_HEADER = struct.Struct(">Q")


class LinkTimeError(Exception):
    """Raised for every failure this module reports; main() turns it into JSON."""


def _ipv4(text: str) -> str:
    try:
        return str(ipaddress.IPv4Address(text))
    except ValueError:
        raise LinkTimeError(f"{text!r} is not an IPv4 address") from None


def _port(text: str) -> int:
    if not (text.isascii() and text.isdigit()) or not 1024 <= int(text) < 65536:
        raise LinkTimeError(f"{text!r} is not a port from 1024 to 65535")
    return int(text)


def _card(text: str) -> int:
    if not (text.isascii() and text.isdigit()):
        raise LinkTimeError(f"{text!r} is not a card index")
    return int(text)


# Thin ctypes wrapper over the few CUDA driver entry points the peer mode needs,
# so the timer does not depend on a Python CUDA binding. Every driver call is
# checked and a non-zero result becomes a LinkTimeError, never a raw error code.
class _Driver:
    """Calls the CUDA driver library directly for contexts, memory and copies."""

    def __init__(self) -> None:
        # Order devices by PCI bus id, so a card index names the same slot on
        # every run and on both ends of the comparison.
        os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
        try:
            self.lib = ctypes.CDLL("libcuda.so.1")
        except OSError as exc:
            raise LinkTimeError(f"no CUDA driver on this machine: {exc}") from None
        self.call("cuInit", ctypes.c_uint(0))

    def call(self, name: str, *args: Any) -> None:
        code = getattr(self.lib, name)(*args)
        if code != 0:
            raise LinkTimeError(f"{name} failed with CUDA error {code}")

    def context(self, card: int) -> tuple[ctypes.c_int, ctypes.c_void_p]:
        device = ctypes.c_int()
        self.call("cuDeviceGet", ctypes.byref(device), ctypes.c_int(card))
        ctx = ctypes.c_void_p()
        self.call("cuDevicePrimaryCtxRetain", ctypes.byref(ctx), device)
        return device, ctx

    def free_bytes(self, ctx: ctypes.c_void_p) -> int:
        self.call("cuCtxSetCurrent", ctx)
        free, total = ctypes.c_size_t(), ctypes.c_size_t()
        self.call("cuMemGetInfo_v2", ctypes.byref(free), ctypes.byref(total))
        return int(free.value)

    def alloc(self, ctx: ctypes.c_void_p, size: int) -> ctypes.c_ulonglong:
        self.call("cuCtxSetCurrent", ctx)
        pointer = ctypes.c_ulonglong()
        self.call("cuMemAlloc_v2", ctypes.byref(pointer), ctypes.c_size_t(size))
        return pointer


def time_peer(card_a: int, card_b: int) -> list[tuple[int, float]]:
    """Copy from card_a to card_b and return (bytes, seconds) per timed copy.

    Nothing is allocated until both cards show HEADROOM_BYTES free beyond the
    largest payload. Every payload size is copied REPEATS times between two
    cuCtxSynchronize calls, so a reading covers the copy itself rather than the
    queueing around it. Contexts and buffers are released in the finally block.
    """
    if card_a == card_b:
        raise LinkTimeError("a peer copy is between two cards, not one")
    driver = _Driver()
    largest = max(PEER_PAYLOADS)
    held: list[tuple[ctypes.c_void_p, ctypes.c_ulonglong]] = []
    devices: list[ctypes.c_int] = []
    try:
        ends = []
        for card in (card_a, card_b):
            device, ctx = driver.context(card)
            devices.append(device)
            free = driver.free_bytes(ctx)
            if free < largest + HEADROOM_BYTES:
                raise LinkTimeError(
                    f"card {card} has {free >> 20} MiB free, and the timer copies "
                    f"to a card only while it keeps {HEADROOM_BYTES >> 20} MiB "
                    "free past its payload"
                )
            pointer = driver.alloc(ctx, largest)
            held.append((ctx, pointer))
            ends.append((ctx, pointer))
        (ctx_a, src), (ctx_b, dst) = ends
        started = time.monotonic()

        def copy(size: int) -> float:
            if time.monotonic() - started > WHOLE_S:
                raise LinkTimeError("the copies outlasted the timer's bound")
            driver.call("cuCtxSetCurrent", ctx_a)
            driver.call("cuCtxSynchronize")
            begin = time.perf_counter()
            driver.call("cuMemcpyPeer", dst, ctx_b, src, ctx_a, ctypes.c_size_t(size))
            driver.call("cuCtxSynchronize")
            return time.perf_counter() - begin

        # Untimed warm-up copy, so first-copy setup costs do not land in a
        # timed reading.
        copy(min(PEER_PAYLOADS))
        return [(size, copy(size)) for size in PEER_PAYLOADS for _ in range(REPEATS)]
    finally:
        for ctx, pointer in held:
            with contextlib.suppress(LinkTimeError):
                driver.call("cuCtxSetCurrent", ctx)
                driver.call("cuMemFree_v2", pointer)
        for device in devices:
            with contextlib.suppress(LinkTimeError):
                driver.call("cuDevicePrimaryCtxRelease_v2", device)


# TCP side of the timer: every message carries an 8-byte length prefix and the
# sink acknowledges each one with a single byte, so a sender's clock covers a
# full round trip. Only payload bytes are counted; the prefixes are not part of
# the accounting.
def _exactly(conn: socket.socket, count: int) -> bytes:
    chunks = []
    while count:
        chunk = conn.recv(min(count, 1 << 20))
        if not chunk:
            raise LinkTimeError("the other end closed mid-message")
        chunks.append(chunk)
        count -= len(chunk)
    return b"".join(chunks)


def sink(address: str, port: int) -> int:
    """Serve one sender and return the payload bytes it delivered.

    Binds and takes a single connection, then reads length-prefixed messages
    until the sender sends a zero length. Each message is acknowledged with one
    byte, and the total must stay within SINK_MOST_BYTES.
    """
    started = time.monotonic()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind((address, port))
        except OSError as exc:
            raise LinkTimeError(f"cannot listen on {address}:{port}: {exc}") from None
        server.listen(1)
        server.settimeout(ACCEPT_S)
        try:
            conn, _ = server.accept()
        # A timed-out accept() fails the run rather than retrying: one sender is
        # supposed to arrive within ACCEPT_S.
        except socket.timeout:  # noqa: UP041
            raise LinkTimeError(
                f"nothing connected to {address}:{port} within {ACCEPT_S:g} s"
            ) from None
    received = 0
    with conn:
        conn.settimeout(IDLE_S)
        while True:
            if time.monotonic() - started > WHOLE_S:
                raise LinkTimeError("the exchange outlasted the timer's bound")
            (size,) = _HEADER.unpack(_exactly(conn, _HEADER.size))
            if size == 0:
                return received
            if received + size > SINK_MOST_BYTES:
                raise LinkTimeError("the sender sent more than a reading needs")
            left = size
            while left:
                left -= len(_exactly(conn, min(left, 1 << 20)))
            received += size
            conn.sendall(b"\x01")


def send(address: str, port: int) -> list[tuple[int, float]]:
    """Time messages pushed to a sink and return (bytes, seconds) per message.

    Connecting is retried until CONNECT_S elapses, so the sender may start
    before the sink is listening. Each reading spans the send plus the sink's
    one-byte acknowledgement; a zero-length header closes the exchange.
    """
    started = time.monotonic()
    conn: socket.socket | None = None
    while conn is None:
        try:
            conn = socket.create_connection((address, port), timeout=5.0)
        except OSError as exc:
            if time.monotonic() - started > CONNECT_S:
                raise LinkTimeError(
                    f"no sink answered at {address}:{port} within {CONNECT_S:g} s: "
                    f"{exc}"
                ) from None
            time.sleep(0.5)
    link: socket.socket = conn
    with link:
        link.settimeout(IDLE_S)
        link.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        def message(size: int) -> float:
            if time.monotonic() - started > WHOLE_S:
                raise LinkTimeError("the exchange outlasted the timer's bound")
            begin = time.perf_counter()
            link.sendall(_HEADER.pack(size) + bytes(size))
            if _exactly(link, 1) != b"\x01":
                raise LinkTimeError("the sink answered with something else")
            return time.perf_counter() - begin

        # Untimed warm-up message, so connection setup and the first-message
        # ramp do not land in a timed reading.
        message(min(NETWORK_PAYLOADS))
        out = [
            (size, message(size)) for size in NETWORK_PAYLOADS for _ in range(REPEATS)
        ]
        link.sendall(_HEADER.pack(0))
    return out


def main(argv: list[str]) -> int:
    try:
        if len(argv) != 4 or argv[0] != LINK_WORD or argv[1] not in MODES:
            raise LinkTimeError(f"usage: {LINK_WORD} {'|'.join(MODES)} A B")
        mode, first, second = argv[1], argv[2], argv[3]
        said: Any
        if mode == "peer":
            said = {"transfers": time_peer(_card(first), _card(second))}
        elif mode == "sink":
            said = {"received": sink(_ipv4(first), _port(second))}
        else:
            said = {"transfers": send(_ipv4(first), _port(second))}
    except (LinkTimeError, OSError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    print(json.dumps(said))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
