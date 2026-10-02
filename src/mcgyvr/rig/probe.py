"""The latency probe: this rig's UDP path to each peer rig, measured before any session.

Before it plans a session the hub asks rigs how well they reach each other
(the hub's ``probe`` feature). ``probe_open`` has the rig open one UDP
socket — on the tunnel's own listen port when no session holds it, so the
probe crosses the same NAT mapping a tunnel would, else on any port — send
the hub's responder a binding request from it (the hub learns the socket's
public address first hand), and answer ``probe_opened`` with the socket's
LAN endpoints and its round trip to the responder. ``probe_run`` names the
peers and a secret per pair: the rig pings every candidate of every peer
``count`` times (which also opens its own NAT to the peers' pings), answers
the peers' pings, sends a train of bulk packets to each peer's first
answering candidate, and within the deadline answers ``probe_result``: per
peer whether it was reached, at which candidate, the median and least round
trip, the loss, and the rate the peer's train arrived at.

What this socket says and answers is bounded so that it reveals nothing but
reachability and timing, and serves nobody else:

* it sends only to addresses the hub named for a peer of this probe, and
  only to addresses a rig may be at (:func:`reachable`: never loopback,
  link-local, multicast, reserved — the limited broadcast among them — or
  unspecified, never this machine's own), so it is no scanner of arbitrary
  hosts;
* it answers only a ping that carries the secret of a peer of the running
  probe and comes from an address the hub named for that peer, with the
  same bytes (a pong is no larger than its ping), and at most
  :data:`MAX_PONGS_PER_PEER` per peer and :data:`MAX_PONGS_PER_S` in all, so
  it is no reflector and no amplifier;
* a pong is taken only for a ping this probe sent, once, from the address it
  was sent to and with the stamp it carried, so a replayed or forged pong
  measures nothing; a bulk train is counted only up to its own length;
* the socket closes when the hub's ``ttl_s`` is up, and every probe ends with
  the agent.
"""

from __future__ import annotations

import contextlib
import ipaddress
import math
import secrets
import select
import socket
import statistics
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from mcgyvr.rig import commands, protocol, sessionwire, udpwire
from mcgyvr.rig.sessionwire import SessionCode

#: The most probes open at once on this rig.
MAX_OPEN = 4
#: Binding requests: rounds, and how long each waits for its answers.
STUN_ATTEMPTS = 3
STUN_WAIT_S = 0.5
#: The size of a ping, and of a bulk packet (the format's largest).
PING_BYTES = udpwire.PROBE_PACKET_MIN_BYTES
BULK_BYTES = udpwire.PROBE_PACKET_MAX_BYTES
#: The most pongs sent to one peer in one run: every ping it may send to
#: every candidate of this rig.
MAX_PONGS_PER_PEER = sessionwire.MAX_PROBE_COUNT * sessionwire.MAX_ENDPOINTS
#: The most pongs sent in any second, over every peer and probe.
MAX_PONGS_PER_S = 500
#: The longest bulk train counted, in packets: the hub's largest train of the
#: smallest packets.
MAX_TRAIN = -(-sessionwire.MAX_PROBE_BULK_BYTES // udpwire.PROBE_PACKET_MIN_BYTES)
#: The longest single wait of a probe's thread, in seconds, so a close is heard.
SLICE_S = 0.05


def reachable(address: ipaddress.IPv4Address) -> bool:
    """Whether ``address`` is one a peer rig, or the hub's responder, may be at."""
    return not (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _ipv4(host: str) -> ipaddress.IPv4Address | None:
    try:
        return ipaddress.IPv4Address(host)
    except ValueError:
        return None


@dataclass
class _Peer:
    rig_id: str
    secret: bytes
    candidates: list[tuple[sessionwire.Endpoint, tuple[str, int]]]
    sent: dict[int, tuple[float, int, int]] = field(default_factory=dict)
    samples: dict[int, list[float]] = field(default_factory=dict)
    pinged: dict[int, int] = field(default_factory=dict)
    first: int | None = None  # the candidate that answered first
    pongs: int = 0
    bulk_sent: bool = False
    train: set[int] = field(default_factory=set)
    train_bytes: int = 0
    train_first: tuple[float, int] | None = None
    train_last: float = 0.0

    def hosts(self) -> set[str]:
        return {address[0] for _, address in self.candidates}


@dataclass(eq=False)
class _Probe:
    asked: sessionwire.ProbeOpen
    sock: socket.socket
    ends_at: float
    opened: bool = False
    stun_rtt_us: int | None = None
    pending: list[str] = field(default_factory=list)
    run: sessionwire.ProbeRun | None = None
    run_id: str | None = None
    run_at: float = 0.0
    peers: dict[bytes, _Peer] = field(default_factory=dict)
    rounds_sent: int = 0
    reported: bool = False
    closed: threading.Event = field(default_factory=threading.Event)


class Probes:
    """This rig's probes: the handlers and one thread per open probe."""

    def __init__(
        self,
        *,
        send: Callable[[str], bool],
        port: Callable[[], int | None],
        hosts: Callable[[], Sequence[str]],
        own: Callable[[], Sequence[ipaddress.IPv4Address]] = tuple,
        allowed: Callable[[ipaddress.IPv4Address], bool] = reachable,
        lending: Callable[[], bool] = lambda: True,
        bind_host: str = "0.0.0.0",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._send = send
        self._lending = lending
        self._port = port
        self._hosts = hosts
        self._own = own
        self._allowed = allowed
        self._bind_host = bind_host
        self._clock = clock
        self._lock = threading.Lock()
        self._probes: dict[str, _Probe] = {}
        self._pong_times: list[float] = []

    # -- what the agent asks -------------------------------------------------

    def close(self) -> None:
        """End every probe now; their sockets close."""
        with self._lock:
            for probe in self._probes.values():
                probe.closed.set()

    def open_count(self) -> int:
        """How many probes hold a socket now."""
        with self._lock:
            return sum(1 for p in self._probes.values() if not p.closed.is_set())

    # -- the handlers --------------------------------------------------------

    def open(self, envelope: protocol.Envelope) -> str | None:
        """``probe_open``: answered ``probe_opened`` once the responder was asked."""
        asked = sessionwire.read_probe_open(envelope)
        if not self._lending():
            return sessionwire.refusal(
                envelope.id, SessionCode.NOT_CAPABLE, "this rig lends nothing"
            )
        with self._lock:
            known = self._probes.get(asked.probe_id)
            if known is not None:
                if known.asked != asked:
                    return sessionwire.refusal(
                        envelope.id,
                        protocol.ErrorCode.BAD_MESSAGE,
                        "probe_id: open with other settings",
                    )
                if known.opened:
                    return self._opened(known, envelope.id)
                known.pending.append(envelope.id)
                return None
            live = [p for p in self._probes.values() if not p.closed.is_set()]
            if len(live) >= MAX_OPEN:
                return sessionwire.refusal(
                    envelope.id, SessionCode.BUSY, "this rig has probes enough open"
                )
            try:
                sock = self._socket()
            except OSError:
                return sessionwire.refusal(
                    envelope.id, SessionCode.NOT_CAPABLE, "no UDP socket opened"
                )
            probe = _Probe(
                asked=asked,
                sock=sock,
                ends_at=self._clock() + asked.ttl_s,
                pending=[envelope.id],
            )
            self._forget_closed()
            self._probes[asked.probe_id] = probe
        threading.Thread(target=self._serve, args=(probe,), daemon=True).start()
        return None

    def run(self, envelope: protocol.Envelope) -> str | None:
        """``probe_run``: answered ``probe_result`` by its deadline."""
        asked = sessionwire.read_probe_run(envelope)
        with self._lock:
            probe = self._probes.get(asked.probe_id)
            if probe is None or probe.closed.is_set() or not probe.opened:
                return sessionwire.refusal(
                    envelope.id, SessionCode.NOT_READY, "probe_id: no such probe open"
                )
            if probe.run is not None:
                return sessionwire.refusal(
                    envelope.id, SessionCode.DUPLICATE, "probe_id: this probe has run"
                )
            peers = {}
            own = set(self._own())
            for peer in asked.peers:
                candidates = []
                for endpoint in peer.endpoints:
                    address = _ipv4(endpoint.host)
                    if address is None or address in own or not self._allowed(address):
                        continue
                    candidates.append((endpoint, (str(address), endpoint.port)))
                peers[peer.secret] = _Peer(
                    rig_id=peer.rig_id, secret=peer.secret, candidates=candidates
                )
            probe.peers = peers
            probe.run = asked
            probe.run_id = envelope.id
            probe.run_at = self._clock()
        return None

    # -- the probe's thread --------------------------------------------------

    def _opened(self, probe: _Probe, re: str) -> str:
        return sessionwire.probe_opened(
            re,
            probe_id=probe.asked.probe_id,
            endpoints=self._endpoints(probe),
            stun_rtt_us=probe.stun_rtt_us,
        )

    def _socket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            wanted = self._port()
            try:
                sock.bind((self._bind_host, wanted or 0))
            except OSError:
                if not wanted:
                    raise
                sock.bind((self._bind_host, 0))
        except OSError:
            sock.close()
            raise
        return sock

    def _forget_closed(self) -> None:
        for probe_id in [k for k, p in self._probes.items() if p.closed.is_set()]:
            del self._probes[probe_id]

    def _endpoints(self, probe: _Probe) -> list[sessionwire.Endpoint]:
        port = int(probe.sock.getsockname()[1])
        return [
            sessionwire.Endpoint(host=host, port=port, kind="lan")
            for host in list(self._hosts())[: sessionwire.MAX_ENDPOINTS]
        ]

    def _serve(self, probe: _Probe) -> None:
        try:
            stun_rtt = self._ask_responder(probe)
            with self._lock:
                probe.stun_rtt_us = stun_rtt
                probe.opened = True
                waiting, probe.pending = probe.pending, []
            for re in waiting:
                self._send(self._opened(probe, re))
            self._loop(probe)
        finally:
            probe.closed.set()
            probe.sock.close()

    def _ask_responder(self, probe: _Probe) -> int | None:
        servers = []
        own = set(self._own())
        for endpoint in probe.asked.stun:
            address = _ipv4(endpoint.host)
            if address is not None and address not in own and self._allowed(address):
                servers.append((str(address), endpoint.port))
        if not servers:
            return None
        try:
            found = udpwire.ask_bindings(
                probe.sock,
                probe.asked.token,
                servers,
                attempts=STUN_ATTEMPTS,
                wait_s=STUN_WAIT_S,
            )
        except OSError:
            return None
        if not found:
            return None
        return min(sessionwire.MAX_RTT_US, min(rtt for rtt, _ in found.values()))

    def _loop(self, probe: _Probe) -> None:
        probe.sock.setblocking(False)
        while not probe.closed.is_set():
            now = self._clock()
            if now >= probe.ends_at and (probe.run is None or probe.reported):
                return
            self._schedule(probe, now)
            ready, _, _ = select.select([probe.sock], [], [], SLICE_S)
            if ready:
                self._drain(probe)

    def _schedule(self, probe: _Probe, now: float) -> None:
        run = probe.run
        if run is None or probe.reported:
            return
        since = now - probe.run_at
        interval = run.interval_ms / 1000
        while probe.rounds_sent < run.count and since >= probe.rounds_sent * interval:
            self._ping_round(probe, probe.rounds_sent)
            probe.rounds_sent += 1
        if run.bulk_bytes and since >= run.count * interval:
            for peer in probe.peers.values():
                if not peer.bulk_sent and peer.first is not None:
                    self._bulk(probe, peer, run.bulk_bytes)
        if since * 1000 >= run.deadline_ms:
            self._report(probe)

    def _ping_round(self, probe: _Probe, round_: int) -> None:
        for peer in probe.peers.values():
            for index, (_, address) in enumerate(peer.candidates):
                seq = round_ * sessionwire.MAX_ENDPOINTS + index
                stamp = secrets.randbits(63)
                with contextlib.suppress(OSError):
                    probe.sock.sendto(
                        udpwire.probe_packet(udpwire.PING, peer.secret, seq, stamp),
                        address,
                    )
                    peer.sent[seq] = (self._clock(), index, stamp)
                    peer.pinged[index] = peer.pinged.get(index, 0) + 1

    def _bulk(self, probe: _Probe, peer: _Peer, total: int) -> None:
        assert peer.first is not None
        peer.bulk_sent = True
        address = peer.candidates[peer.first][1]
        packets = max(1, math.ceil(total / BULK_BYTES))
        for seq in range(packets):
            size = max(udpwire.PROBE_PACKET_MIN_BYTES, min(BULK_BYTES, total))
            total -= size
            with contextlib.suppress(OSError):
                probe.sock.sendto(
                    udpwire.probe_packet(
                        udpwire.BULK, peer.secret, seq, packets, size=size
                    ),
                    address,
                )

    def _drain(self, probe: _Probe) -> None:
        while True:
            try:
                data, source = probe.sock.recvfrom(udpwire.RECEIVE_BYTES)
            except (BlockingIOError, InterruptedError):
                return
            except OSError:
                return
            self._take(probe, data, (str(source[0]), int(source[1])))

    def _take(self, probe: _Probe, data: bytes, source: tuple[str, int]) -> None:
        packet = udpwire.read_probe(data)
        if packet is None or probe.run is None:
            return
        peer = probe.peers.get(packet.secret)
        if peer is None or source[0] not in peer.hosts():
            return
        now = self._clock()
        if packet.kind == udpwire.PING:
            if peer.pongs >= MAX_PONGS_PER_PEER or not self._may_pong(now):
                return
            answer = udpwire.pong(data)
            if answer is not None:
                peer.pongs += 1
                with contextlib.suppress(OSError):
                    probe.sock.sendto(answer, source)
            return
        if packet.kind == udpwire.PONG:
            sent = peer.sent.pop(packet.seq, None)
            if sent is None:
                return
            at, index, stamp = sent
            if stamp != packet.stamp or peer.candidates[index][1][0] != source[0]:
                return
            peer.samples.setdefault(index, []).append(now - at)
            if peer.first is None:
                peer.first = index
            return
        if packet.seq in peer.train or not 0 <= packet.seq < packet.stamp <= MAX_TRAIN:
            return
        peer.train.add(packet.seq)
        peer.train_bytes += packet.size
        if peer.train_first is None:
            peer.train_first = (now, packet.size)
        peer.train_last = now

    def _may_pong(self, now: float) -> bool:
        with self._lock:
            self._pong_times = [t for t in self._pong_times if now - t < 1.0]
            if len(self._pong_times) >= MAX_PONGS_PER_S:
                return False
            self._pong_times.append(now)
            return True

    def _report(self, probe: _Probe) -> None:
        assert probe.run is not None and probe.run_id is not None
        probe.reported = True
        results = [self._outcome(peer) for peer in probe.peers.values()]
        self._send(
            sessionwire.probe_result(
                probe.run_id, probe_id=probe.run.probe_id, results=results
            )
        )

    def _outcome(self, peer: _Peer) -> sessionwire.ProbeOutcome:
        if peer.first is None:
            return sessionwire.ProbeOutcome(rig_id=peer.rig_id, reached=False)
        index = peer.first
        samples = peer.samples[index]
        pinged = max(1, peer.pinged.get(index, 1))
        rate = None
        if peer.train_first is not None and peer.train_last > peer.train_first[0]:
            bits = (peer.train_bytes - peer.train_first[1]) * 8
            kbps = bits / 1000 / (peer.train_last - peer.train_first[0])
            rate = max(1, min(sessionwire.MAX_RATE_KBPS, round(kbps)))
        return sessionwire.ProbeOutcome(
            rig_id=peer.rig_id,
            reached=True,
            endpoint=peer.candidates[index][0],
            rtt_us=_us(statistics.median(samples)),
            rtt_min_us=_us(min(samples)),
            loss_pct=max(0, min(100, round(100 * (pinged - len(samples)) / pinged))),
            rate_kbps=rate,
        )


def _us(seconds: float) -> int:
    return max(0, min(sessionwire.MAX_RTT_US, round(seconds * 1_000_000)))


def register(dispatcher: commands.Dispatcher, probes: Probes) -> None:
    """Handle the hub's probe commands with ``probes``."""
    dispatcher.register("probe_open", lambda envelope, _: probes.open(envelope))
    dispatcher.register("probe_run", lambda envelope, _: probes.run(envelope))
