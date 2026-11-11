"""A ring peer is walked beside the head and never fails or holds the session up.

A worker may be named a second worker as a tunnel peer (``tunnel_up`` peer
``ring``: the worker <-> worker link of a ring, feature ``ring_peers``) only
when its owner turned the ring links on (``ring_links``, off until set): a
rig without it names no ``ring_peers`` and refuses such a peer, and a head
refuses one whatever it names. Such a peer is optional. It is walked beside
the head, in the same loop and under the same deadline, never through the
birthday dance; once the head has settled, a ring peer still walking is given
up at once, so it never stretches the bring-up. A ring peer no path reaches,
one whose path is too narrow, and one left out of the tunnel, never
configured (nothing this rig may aim at but birthday candidates, or an
identity the pins refuse) are all reported ``none``, and the session comes up
all the same; its relay is never bound, its round trip is no link sample and
it sets no pin. The peer the session needs is held to every rule it always
was.

Once the worker starts, a ring peer that came up may dial exactly the ports
it is named to accept (``accept_ports``), and this rig may dial the peer's
``dial_ports`` on its tunnel address: TCP inside the tunnel only, its replies
back to the local ephemeral range; nothing on eth0. A ring peer in the tunnel
that did not come up is let in on no rpc port and dialled on none, and keeps
no eth0 rule; its WireGuard peer and the wg0 ICMP echo rules every tunnel peer
gets at tunnel-up stay until the session's tunnel goes.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mcgyvr import hubwire
from mcgyvr.rig import identity, pooled, protocol, session, sessionwire, sharing
from tests import rig_pool_fakes as fakes
from tests import rig_schema
from tests.rig_pool_fakes import Pool, make_pool

RING_KEY = "C" * 42 + "w="
RING_ADDRESS = "192.0.2.30"
RING_PEER = "198.51.100.3"
TOKEN = "00112233445566778899aabbccddeeff"
STUN = "203.0.113.9"


@pytest.fixture
def pool(tmp_path: Path) -> Iterator[Pool]:
    made = make_pool(tmp_path, ring_links=True)
    yield made
    made.sessions.close()


def _prepare(pool: Pool) -> None:
    traversal = {"token": TOKEN, "stun": [{"host": STUN, "port": 3478, "kind": "stun"}]}
    assert (
        pool.ask(
            "session_prepare", "p1", session_id="s1", role="worker", traversal=traversal
        )
        is None
    )
    pool.wait_for("session_prepared")


def _ring_peer(
    endpoints: list[dict[str, Any]] | None = None, **ring: Any
) -> dict[str, Any]:
    return {
        "rig_id": "rig-ring",
        "public_key": RING_KEY,
        "endpoints": (
            endpoints
            if endpoints is not None
            else [{"host": RING_ADDRESS, "port": 51820, "kind": "lan"}]
        ),
        "allowed_ips": [f"{RING_PEER}/32"],
        "ring": ring or {"dial_ports": [50052], "accept_ports": [50053]},
    }


def _body(*ring_peers: dict[str, Any], **changes: Any) -> dict[str, Any]:
    body = fakes.tunnel_up_body(**changes)
    body["peers"] += list(ring_peers)
    return body


def _scripts(pool: Pool, script: str) -> list[tuple[str, ...]]:
    return [args for _, s, args in pool.docker.scripts if s == script]


def _start_worker(pool: Pool) -> None:
    ack = pool.ask(
        "worker_start", "w1", session_id="s1", cards=[{"card_index": 1, "port": 50053}]
    )
    assert ack is not None and ack["type"] == "ack", ack
    pool.wait_for("session_status", "ready")


def _paths(report: dict[str, Any]) -> dict[str, str]:
    return {p["rig_id"]: p["path"] for p in report["body"]["peers"]}


def test_a_ring_peer_that_answers_is_reported_and_opened_to_its_ports_alone(
    pool: Pool,
) -> None:
    _prepare(pool)
    report = pool.up("t1", **_body(_ring_peer()))
    assert _paths(report) == {"rig-peer": "lan", "rig-ring": "lan"}
    assert pool.sessions.state_of("s1") == ("tunnel_up", "worker")
    _start_worker(pool)
    # the head and the ring peer named to dial in on 50053 reach that port
    assert _scripts(pool, pooled.OPEN_WORKER_SCRIPT) == [
        (fakes.SELF, "50053", f"{fakes.PEER}/32", f"{RING_PEER}/32")
    ]
    # and this rig may dial the ring peer's 50052 on its tunnel address
    assert _scripts(pool, pooled.OPEN_RING_SCRIPT) == [(fakes.SELF, RING_PEER, "50052")]


def test_a_ring_peers_round_trip_is_never_sent_as_a_link_sample(pool: Pool) -> None:
    _prepare(pool)
    report = pool.up("t1", **_body(_ring_peer()))
    # both walks timed a round trip; the report carries each beside its path
    assert {p["rig_id"] for p in report["body"]["peers"] if "rtt_us" in p} == {
        "rig-peer",
        "rig-ring",
    }
    pool.settle()
    # but peer_rtt, which the hub records as a link it plans on, names the head alone
    (frame,) = pool.box.of_type("peer_rtt")
    assert [s["rig_id"] for s in frame["body"]["samples"]] == ["rig-peer"]


def test_a_ring_peer_named_only_to_dial_in_opens_no_dial(pool: Pool) -> None:
    _prepare(pool)
    pool.up("t1", **_body(_ring_peer(accept_ports=[50053])))
    _start_worker(pool)
    assert _scripts(pool, pooled.OPEN_WORKER_SCRIPT) == [
        (fakes.SELF, "50053", f"{fakes.PEER}/32", f"{RING_PEER}/32")
    ]
    assert _scripts(pool, pooled.OPEN_RING_SCRIPT) == []


def test_a_ring_peer_this_rig_only_dials_is_not_let_in(pool: Pool) -> None:
    _prepare(pool)
    pool.up("t1", **_body(_ring_peer(dial_ports=[50052])))
    _start_worker(pool)
    assert _scripts(pool, pooled.OPEN_WORKER_SCRIPT) == [
        (fakes.SELF, "50053", f"{fakes.PEER}/32")
    ]
    assert _scripts(pool, pooled.OPEN_RING_SCRIPT) == [(fakes.SELF, RING_PEER, "50052")]


def test_a_dead_ring_peer_leaves_the_session_up_and_is_let_in_on_no_port(
    pool: Pool,
) -> None:
    pool.docker.answering = {(fakes.PEER_ADDRESS, 51820)}
    _prepare(pool)
    report = pool.up("t1", **_body(_ring_peer()))
    assert _paths(report) == {"rig-peer": "lan", "rig-ring": "none"}
    assert pool.sessions.state_of("s1") == ("tunnel_up", "worker")
    # it was in the tunnel (its WireGuard peer and wg0 ICMP rules, which stay) ...
    (up,) = _scripts(pool, pooled.TUNNEL_SCRIPT)
    assert RING_KEY in up and f"{RING_PEER}/32" in up
    # ... but the dead peer is left unaimed: no UDP rule for it on eth0
    assert RING_ADDRESS not in _scripts(pool, pooled.PATH_SCRIPT)[-1]
    _start_worker(pool)
    assert _scripts(pool, pooled.OPEN_WORKER_SCRIPT) == [
        (fakes.SELF, "50053", f"{fakes.PEER}/32")
    ]
    assert _scripts(pool, pooled.OPEN_RING_SCRIPT) == []
    assert any("no ring link to rig-ring" in line for line in pool.logged)


def test_a_dead_ring_peer_is_given_up_once_the_head_settles_not_at_the_deadline(
    pool: Pool,
) -> None:
    pool.docker.answering = {(fakes.PEER_ADDRESS, 51820)}
    _prepare(pool)
    began = time.monotonic()
    # each of the ring peer's candidates would be aimed at for a whole second,
    # and the walk is given 30 s to connect
    many = [{"host": f"192.0.2.{n}", "port": 51820, "kind": "lan"} for n in (31, 32)]
    report = pool.up("t1", **_body(_ring_peer(many), attempt_s=1, connect_timeout_s=30))
    took = time.monotonic() - began
    assert _paths(report) == {"rig-peer": "lan", "rig-ring": "none"}
    assert took < 1.0, took
    assert pool.sessions.state_of("s1") == ("tunnel_up", "worker")


def test_a_ring_peer_whose_path_is_too_narrow_is_none_and_fails_nothing(
    pool: Pool,
) -> None:
    pool.docker.narrow = {(RING_ADDRESS, 51820)}
    _prepare(pool)
    report = pool.up("t1", **_body(_ring_peer()))
    assert report["type"] == "tunnel_report"
    assert _paths(report) == {"rig-peer": "lan", "rig-ring": "none"}
    assert pool.sessions.state_of("s1") == ("tunnel_up", "worker")


def test_a_ring_peer_with_nothing_to_aim_at_is_left_out_and_reported_none(
    pool: Pool,
) -> None:
    _prepare(pool)
    loopback = [{"host": "127.0.0.1", "port": 51820, "kind": "lan"}]
    report = pool.up("t1", **_body(_ring_peer(loopback)))
    assert _paths(report) == {"rig-peer": "lan", "rig-ring": "none"}
    (up,) = _scripts(pool, pooled.TUNNEL_SCRIPT)
    assert RING_KEY not in up and "127.0.0.1" not in up
    assert pool.sessions.state_of("s1") == ("tunnel_up", "worker")


BIRTHDAY = [
    {"host": "203.0.113.40", "port": 6000, "kind": "birthday", "ports": 64},
    {"host": "203.0.113.41", "port": 4000, "kind": "birthday_burst", "ports": 16},
]


def _danced(pool: Pool) -> list[tuple[str, ...]]:
    """The birthday dances the rig ran in its tunnel container."""
    return [args for _, _, args in pool.docker.python if args[:1] == ("birthday",)]


def test_a_ring_peer_with_birthday_candidates_alone_never_dances_and_is_none(
    pool: Pool,
) -> None:
    _prepare(pool)
    report = pool.up("t1", **_body(_ring_peer(BIRTHDAY)))
    assert _paths(report) == {"rig-peer": "lan", "rig-ring": "none"}
    assert pool.sessions.state_of("s1") == ("tunnel_up", "worker")
    assert _danced(pool) == []
    # nothing else to aim at, so it was left out of the tunnel
    (up,) = _scripts(pool, pooled.TUNNEL_SCRIPT)
    assert RING_KEY not in up


def test_a_ring_peer_walks_its_other_candidates_and_skips_the_dance(
    pool: Pool,
) -> None:
    # the head is reached only at its second candidate, so the ring walk would
    # have reached its birthday candidate while the head's walk was still open
    pool.docker.answering = {(fakes.PEER_ADDRESS, 51821), (RING_ADDRESS, 51820)}
    _prepare(pool)
    body = _body(
        _ring_peer([*BIRTHDAY, {"host": RING_ADDRESS, "port": 51820, "kind": "lan"}])
    )
    body["peers"][0]["endpoints"] = [
        {"host": fakes.PEER_ADDRESS, "port": port, "kind": "lan"}
        for port in (51820, 51821)
    ]
    report = pool.up("t1", **body)
    assert _danced(pool) == []
    assert _paths(report) == {"rig-peer": "lan", "rig-ring": "lan"}
    (up,) = _scripts(pool, pooled.TUNNEL_SCRIPT)
    assert "203.0.113.40" not in up and "203.0.113.41" not in up


def test_the_peer_the_session_needs_still_dances_at_its_birthday_candidate(
    pool: Pool,
) -> None:
    _prepare(pool)
    body = _body(_ring_peer())
    body["peers"][0]["endpoints"] = BIRTHDAY[:1]
    report = pool.up("t1", **body)
    assert _paths(report) == {"rig-peer": "direct", "rig-ring": "lan"}
    probe = ("birthday", "probe", "51820", "203.0.113.40", "6000", "64")
    assert _danced(pool) == [probe]


def test_the_peer_the_session_needs_with_nothing_to_aim_at_is_still_refused(
    pool: Pool,
) -> None:
    _prepare(pool)
    body = _body(_ring_peer())
    loopback = {"host": "127.0.0.1", "port": 51820, "kind": "lan"}
    body["peers"][0]["endpoints"] = [loopback]
    refused = pool.ask("tunnel_up", "t1", **body)
    assert refused is not None and refused["body"]["code"] == "tunnel_failed"
    assert "no endpoint or relay" in refused["body"]["message"]
    pool.settle()
    assert _scripts(pool, pooled.TUNNEL_SCRIPT) == []


def test_a_ring_peers_relay_is_never_bound(pool: Pool) -> None:
    pool.docker.answering = {(fakes.PEER_ADDRESS, 51820)}
    _prepare(pool)
    ring = _ring_peer()
    ring["relay"] = {"host": "203.0.113.50", "port": 3478, "ticket": "T" * 30}
    report = pool.up("t1", **_body(ring))
    assert _paths(report)["rig-ring"] == "none"
    assert pool.relayed == []


def test_a_tunnel_of_ring_peers_alone_is_refused(pool: Pool) -> None:
    _prepare(pool)
    body = fakes.tunnel_up_body(peers=[_ring_peer()])
    refused = pool.ask("tunnel_up", "t1", **body)
    assert refused is not None and refused["body"]["code"] == "bad_message"
    pool.settle()
    assert _scripts(pool, pooled.TUNNEL_SCRIPT) == []


def test_the_sessions_head_refuses_a_ring_peer_as_a_bad_message(pool: Pool) -> None:
    # every worker is one the head needs: none is ever optional to it
    fakes.prepared(pool, role="head")
    refused = pool.ask("tunnel_up", "t1", **_body(_ring_peer()))
    assert refused is not None and refused["body"]["code"] == "bad_message"
    assert "the session's head" in refused["body"]["message"]
    pool.settle()
    assert _scripts(pool, pooled.TUNNEL_SCRIPT) == []
    # the same head takes the star it always took
    assert pool.up("t2", **fakes.tunnel_up_body())["type"] == "tunnel_report"


def test_a_rig_without_ring_links_refuses_a_ring_peer(tmp_path: Path) -> None:
    pool = make_pool(tmp_path)
    try:
        _prepare(pool)
        refused = pool.ask("tunnel_up", "t1", **_body(_ring_peer()))
        assert refused is not None and refused["body"]["code"] == "not_capable"
        pool.settle()
        assert _scripts(pool, pooled.TUNNEL_SCRIPT) == []
    finally:
        pool.sessions.close()


def _identity() -> identity.Identity:
    return identity.Identity(Ed25519PrivateKey.generate())


#: What a peer's identity check refuses (:func:`mcgyvr.rig.identity.vet_peer`),
#: and the words its refusal names.
FAULTS = {
    "changed": "identity key changed",
    "forged": "not signed",
    "unsigned": "not signed",
    "unnamed": "sends none",
}


def _fault(pins: identity.Pins, peer: dict[str, Any], fault: str) -> None:
    """Give `peer` (a tunnel_up peer entry) the identity `fault`: a key other
    than the one pinned for it, a tunnel key its identity did not sign, no
    signature, or no key at all for a peer pinned once."""
    first, now = _identity(), _identity()
    if fault in ("changed", "unnamed"):
        pins.pin(peer["rig_id"], first.public_key)
    if fault == "unnamed":
        return
    peer[hubwire.IDENTITY_KEY_FIELD] = now.public_key
    if fault == "changed":
        signer = now
    elif fault == "forged":
        signer = _identity()
    else:
        return
    peer[hubwire.SESSION_KEY_SIG_FIELD] = signer.sign_session_key(
        "s1", peer["public_key"]
    )


def _signed(peer: dict[str, Any], who: identity.Identity) -> dict[str, Any]:
    peer[hubwire.IDENTITY_KEY_FIELD] = who.public_key
    peer[hubwire.SESSION_KEY_SIG_FIELD] = who.sign_session_key("s1", peer["public_key"])
    return peer


@pytest.mark.parametrize("fault", sorted(FAULTS))
def test_a_ring_peer_the_identity_check_refuses_is_left_out_and_the_session_comes_up(
    fault: str, tmp_path: Path
) -> None:
    pins = identity.Pins(tmp_path / "pins.json")
    ring = _ring_peer()
    _fault(pins, ring, fault)
    before = pins.all()
    pool = make_pool(
        tmp_path / "pool", ring_links=True, rig_identity=_identity(), pins=pins
    )
    try:
        _prepare(pool)
        report = pool.up("t1", **_body(ring))
        assert _paths(report) == {"rig-peer": "lan", "rig-ring": "none"}
        assert pool.sessions.state_of("s1") == ("tunnel_up", "worker")
        # never configured: no WireGuard peer, no rule, no aim for it
        (up,) = _scripts(pool, pooled.TUNNEL_SCRIPT)
        assert RING_KEY not in up and f"{RING_PEER}/32" not in up
        assert RING_ADDRESS not in up
        assert all(RING_KEY not in args for args in _scripts(pool, pooled.PATH_SCRIPT))
        _start_worker(pool)
        assert _scripts(pool, pooled.OPEN_WORKER_SCRIPT) == [
            (fakes.SELF, "50053", f"{fakes.PEER}/32")
        ]
        assert _scripts(pool, pooled.OPEN_RING_SCRIPT) == []
        (left,) = [line for line in pool.logged if "left out of the tunnel" in line]
        assert "ring peer rig-ring" in left and FAULTS[fault] in left
        # and no pin was set or changed by it
        assert pins.all() == before
    finally:
        pool.sessions.close()


@pytest.mark.parametrize("fault", sorted(FAULTS))
def test_the_peer_the_session_needs_failing_the_identity_check_still_refuses_it(
    fault: str, tmp_path: Path
) -> None:
    pins = identity.Pins(tmp_path / "pins.json")
    body = _body(_signed(_ring_peer(), _identity()))
    _fault(pins, body["peers"][0], fault)
    before = pins.all()
    pool = make_pool(
        tmp_path / "pool", ring_links=True, rig_identity=_identity(), pins=pins
    )
    try:
        _prepare(pool)
        refused = pool.ask("tunnel_up", "t1", **body)
        assert refused is not None and refused["type"] == "error"
        assert refused["body"]["code"] == sessionwire.SessionCode.TUNNEL_FAILED
        assert "peer rig-peer" in refused["body"]["message"]
        assert FAULTS[fault] in refused["body"]["message"]
        pool.settle()
        assert _scripts(pool, pooled.TUNNEL_SCRIPT) == []
        assert pins.all() == before
    finally:
        pool.sessions.close()


SECOND_KEY = "D" * 42 + "w="


def _second_ring_peer(**changes: Any) -> dict[str, Any]:
    peer = _ring_peer([{"host": "192.0.2.31", "port": 51820, "kind": "lan"}])
    peer.update(rig_id="rig-ring-2", public_key=SECOND_KEY)
    peer["allowed_ips"] = ["198.51.100.4/32"]
    peer.update(changes)
    return peer


def test_a_ring_peer_under_the_needed_peers_wireguard_key_is_a_bad_message(
    tmp_path: Path,
) -> None:
    # a hub copies the head's key, identity key and signature into a ring entry
    # under another rig id: the signature holds, but the second `wg set` would
    # take the head's allowed-ips away
    pins = identity.Pins(tmp_path / "pins.json")
    head = _identity()
    body = _body(_ring_peer())
    needed, ring = body["peers"]
    _signed(needed, head)
    ring["public_key"] = needed["public_key"]
    ring[hubwire.IDENTITY_KEY_FIELD] = needed[hubwire.IDENTITY_KEY_FIELD]
    ring[hubwire.SESSION_KEY_SIG_FIELD] = needed[hubwire.SESSION_KEY_SIG_FIELD]
    pool = make_pool(
        tmp_path / "pool", ring_links=True, rig_identity=_identity(), pins=pins
    )
    try:
        _prepare(pool)
        refused = pool.ask("tunnel_up", "t1", **body)
        assert refused is not None and refused["body"]["code"] == "bad_message"
        assert "public_key is another peer's" in refused["body"]["message"]
        pool.settle()
        assert _scripts(pool, pooled.TUNNEL_SCRIPT) == []
        assert pins.all() == {}
    finally:
        pool.sessions.close()


def test_two_ring_peers_under_one_wireguard_key_are_a_bad_message(pool: Pool) -> None:
    _prepare(pool)
    body = _body(_ring_peer(), _second_ring_peer(public_key=RING_KEY))
    refused = pool.ask("tunnel_up", "t1", **body)
    assert refused is not None and refused["body"]["code"] == "bad_message"
    pool.settle()
    assert _scripts(pool, pooled.TUNNEL_SCRIPT) == []


def test_ring_peers_under_keys_of_their_own_are_taken(pool: Pool) -> None:
    _prepare(pool)
    report = pool.up("t1", **_body(_ring_peer(), _second_ring_peer()))
    assert _paths(report) == {"rig-peer": "lan", "rig-ring": "lan", "rig-ring-2": "lan"}


def test_two_needed_peers_under_one_key_are_read_and_taken_as_they_always_were(
    tmp_path: Path,
) -> None:
    # no ring peer: the duplicate-key refusal is the ring link's alone, and a
    # head's two workers under one key are what they were before ring_peers
    body = fakes.tunnel_up_body()
    twin = dict(body["peers"][0], rig_id="rig-twin", allowed_ips=["198.51.100.5/32"])
    body["peers"].append(twin)
    frame = json.dumps({"v": 1, "type": "tunnel_up", "id": "t1", "body": body})
    read = sessionwire.read_tunnel_up(protocol.decode(frame))
    assert [p.public_key for p in read.peers] == [fakes.PEER_KEY, fakes.PEER_KEY]
    pool = make_pool(tmp_path, ring_links=True)
    try:
        fakes.prepared(pool, role="head")
        assert pool.up("t1", **body)["type"] == "tunnel_report"
        (up,) = _scripts(pool, pooled.TUNNEL_SCRIPT)
        assert up.count(fakes.PEER_KEY) == 2
    finally:
        pool.sessions.close()


def test_a_ring_peer_carrying_another_rigs_identity_and_signature_is_left_out(
    tmp_path: Path,
) -> None:
    # the same copy with a WireGuard key of its own: the signature covers the
    # session and the WireGuard key, so it does not hold for the ring entry's
    pins = identity.Pins(tmp_path / "pins.json")
    head = _identity()
    body = _body(_ring_peer())
    needed, ring = body["peers"]
    _signed(needed, head)
    ring[hubwire.IDENTITY_KEY_FIELD] = needed[hubwire.IDENTITY_KEY_FIELD]
    ring[hubwire.SESSION_KEY_SIG_FIELD] = needed[hubwire.SESSION_KEY_SIG_FIELD]
    pool = make_pool(
        tmp_path / "pool", ring_links=True, rig_identity=_identity(), pins=pins
    )
    try:
        _prepare(pool)
        report = pool.up("t1", **body)
        assert _paths(report) == {"rig-peer": "lan", "rig-ring": "none"}
        (up,) = _scripts(pool, pooled.TUNNEL_SCRIPT)
        assert RING_KEY not in up
        (left,) = [line for line in pool.logged if "left out of the tunnel" in line]
        assert "ring peer rig-ring" in left and "not signed" in left
        assert pins.all() == {"rig-peer": head.public_key}
    finally:
        pool.sessions.close()


def test_a_ring_peer_taken_pins_nothing_and_the_peer_the_session_needs_is_pinned(
    tmp_path: Path,
) -> None:
    pins = identity.Pins(tmp_path / "pins.json")
    needed, ring = _identity(), _identity()
    body = _body(_signed(_ring_peer(), ring))
    _signed(body["peers"][0], needed)
    pool = make_pool(
        tmp_path / "pool", ring_links=True, rig_identity=_identity(), pins=pins
    )
    try:
        _prepare(pool)
        report = pool.up("t1", **body)
        assert _paths(report) == {"rig-peer": "lan", "rig-ring": "lan"}
        # the optional link is checked against the pins but sets none
        assert pins.all() == {"rig-peer": needed.public_key}
    finally:
        pool.sessions.close()


@pytest.mark.parametrize(
    "ring",
    [
        {},
        {"dial_ports": []},
        {"dial_ports": [0]},
        {"dial_ports": [65536]},
        {"accept_ports": [50053, 50053]},
        {"dial_ports": "50052"},
        {"dial_ports": list(range(50000, 50000 + hubwire.MAX_RING_PORTS + 1))},
        [],
    ],
)
def test_a_ring_link_of_no_port_or_a_bad_one_is_refused_as_a_bad_message(
    ring: Any,
) -> None:
    body = _body(_ring_peer())
    body["peers"][1]["ring"] = ring
    frame = json.dumps({"v": 1, "type": "tunnel_up", "id": "t1", "body": body})
    with pytest.raises(protocol.ProtocolError):
        sessionwire.read_tunnel_up(protocol.decode(frame))


def test_a_peer_without_ring_is_read_as_one_the_session_needs() -> None:
    frame = json.dumps(
        {"v": 1, "type": "tunnel_up", "id": "t1", "body": _body(_ring_peer())}
    )
    needed, ring = sessionwire.read_tunnel_up(protocol.decode(frame)).peers
    assert needed.ring is None
    assert ring.ring == sessionwire.RingLink(dial_ports=(50052,), accept_ports=(50053,))


def test_the_ring_script_opens_tcp_inside_the_tunnel_only() -> None:
    script = pooled.OPEN_RING_SCRIPT
    assert "eth0" not in script and "udp" not in script
    assert (
        "output oifname wg0 ip saddr $self ip daddr $1 \\\ntcp dport $2 accept"
    ) in script
    assert (
        "input iifname wg0 ip saddr $1 ip daddr $self \\\n"
        "tcp sport $2 tcp dport $low-$high accept"
    ) in script
    assert "ip_local_port_range" in script


def test_the_rig_names_ring_peers_only_once_its_owner_turned_them_on(
    tmp_path: Path,
) -> None:
    held = fakes.inventory(tmp_path)
    off = session.offer(
        fakes.sharing(tmp_path), held, (fakes.LAN_ADDRESS,), (), fakes.report()
    )
    on = session.offer(
        fakes.sharing(tmp_path, ring_links=True),
        held,
        (fakes.LAN_ADDRESS,),
        (),
        fakes.report(),
    )
    assert session.RING_PEERS_FEATURE not in off.features
    assert session.RING_PEERS_FEATURE not in session.FEATURES
    assert on.features == (*off.features, session.RING_PEERS_FEATURE)
    assert session.RING_PEERS_FEATURE == hubwire.FEATURE_RING_PEERS
    assert hubwire.FEATURE_RING_PEERS in rig_schema.load()["x-features"]


def test_ring_links_are_off_and_unwritten_until_the_owner_sets_them() -> None:
    assert sharing.Sharing().ring_links is False
    assert "ring_links" not in sharing.as_data(sharing.Sharing())
    on = sharing.read({"ring_links": True})
    assert on.ring_links is True
    assert sharing.as_data(on)["ring_links"] is True
    with pytest.raises(sharing.SharingError):
        sharing.read({"ring_links": "yes"})


@pytest.mark.parametrize("system", ["darwin", "windows"])
def test_a_native_rig_never_names_ring_peers_since_its_helper_holds_no_worker(
    system: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.native_pool_fakes import as_native_system

    as_native_system(monkeypatch, system)
    share = fakes.sharing(tmp_path, launcher="native", image=None, ring_links=True)
    assert share.native_here()
    offer = session.offer(
        share, fakes.inventory(tmp_path), (fakes.LAN_ADDRESS,), (), fakes.report()
    )
    assert session.RING_PEERS_FEATURE not in offer.features
