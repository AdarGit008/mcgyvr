#!/usr/bin/env python3
"""Time one link between two cards, in one module a rig can run as it is.

``python -m mcgyvr.serving.run link`` ships this very file to a rig as
``python3 - mcgyvr-linktime MODE ARGS`` (gate ``link-01-time.py``), where it
times a few small transfers and prints them as one line of JSON. It imports the
standard library and nothing else, for the same reason the lock's harness does:
the rig has no mcgyvr to import.

Three modes, each a part of one reading:

``peer GPU_A GPU_B``
    Copies from one card of the rig to another, through the CUDA driver
    (``libcuda.so.1``, which every machine with an NVIDIA driver has), with the
    cards numbered in bus order as a split unit's launch numbers them. The bus
    between two cards is what a split over them crosses.

``sink ADDR PORT``
    One end of the network between two rigs: listen on ``ADDR:PORT`` (the
    address the head reaches this worker at), take one connection, and answer
    every message with one byte.

``send ADDR PORT``
    The other end: connect to the sink, and time each message from its first
    byte out to the answer back.

**Bounded and leaving nothing.** Every payload is at most :data:`PEER_PAYLOADS`'
or :data:`NETWORK_PAYLOADS`' largest, a card is copied to only while it has
:data:`HEADROOM_BYTES` free past the payload, the sink takes one connection and
no more than :data:`SINK_MOST_BYTES`, and every mode ends within
:data:`WHOLE_S`. Nothing is written to the rig's disk, and the two buffers a
peer copy allocates are freed before it exits.

What is printed: ``{"transfers": [[bytes, seconds], ...]}`` on success (the
sink prints ``{"received": bytes}``), ``{"error": "..."}`` otherwise, with a
non-zero exit. :mod:`mcgyvr.serving.interconnect` fits the line through the
transfers; this module never fits and never keeps anything.
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

#: The word the door names this timer by on the rig.
LINK_WORD = "mcgyvr-linktime"
#: The timer's modes.
MODES = ("peer", "sink", "send")
#: The port a sink listens on when the probe names none: one the head can reach
#: on the worker's bind address, as it reaches the worker's own processes.
LINK_PORT = 50151

#: Card-to-card payloads, bytes: a small one, where latency is most of the time,
#: and two larger, where bandwidth is. Each is copied :data:`REPEATS` times.
PEER_PAYLOADS = (1 << 16, 1 << 20, 1 << 23)
#: Machine-to-machine payloads, bytes, chosen the same way.
NETWORK_PAYLOADS = (1 << 12, 1 << 18, 1 << 22)
#: How many times each payload is timed.
REPEATS = 3
#: What a card must still have free past a payload before it is copied to, so
#: the timer never takes room a unit on that card is about to need.
HEADROOM_BYTES = 256 << 20
#: The most a sink reads before it ends the exchange: every payload the sender
#: sends, each repeat and its warm-up, and nothing more.
SINK_MOST_BYTES = (sum(NETWORK_PAYLOADS) * (REPEATS + 1)) + 64
#: How long a sink waits for its one connection, and a sender for the sink.
ACCEPT_S = 60.0
CONNECT_S = 30.0
#: How long either end waits on the other for one message or its answer.
IDLE_S = 15.0
#: The bound on a whole mode, whatever it waits on.
WHOLE_S = 120.0

#: A message's header: the payload's length in bytes, big-endian.
_HEADER = struct.Struct(">Q")


class LinkTimeError(Exception):
    """The link could not be timed; the message says why."""


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


# --------------------------------------------------------------------------
# card to card, through the CUDA driver
# --------------------------------------------------------------------------


class _Driver:
    """The few CUDA driver calls a peer copy needs, each checked."""

    def __init__(self) -> None:
        # The launch pins the cards to bus order; so does this, before cuInit.
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
    """Timed copies from ``card_a`` to ``card_b``, each payload timed
    :data:`REPEATS` times."""
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

        # One copy first, not kept: it pays for setting the path up.
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


# --------------------------------------------------------------------------
# machine to machine, over TCP
# --------------------------------------------------------------------------


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
    """Take one connection on ``address:port`` and answer each message; bytes read."""
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
        # socket.timeout, not TimeoutError: a rig's Python 3.8 keeps them apart.
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
    """Timed messages to the sink at ``address:port``, each payload timed
    :data:`REPEATS` times."""
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

        # One message first, not kept: it pays for the connection's slow start.
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
