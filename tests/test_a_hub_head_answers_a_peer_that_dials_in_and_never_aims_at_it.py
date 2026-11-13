"""A hub head answers a peer that dials in, and never aims at it.

A ``tunnel_up`` peer may be a listen peer (``listen``): a worker behind a NAT
that only dials out, to a head whose port it can reach. The field is read only
by a rig that names ``hub_head``, and no rig names it yet, so a peer marked
``listen`` is read, planned, written to the tunnel and walked exactly as the
same peer without the mark.

For a rig that names it (with the settings its session was prepared under), a
listen peer is planned with its key, keepalive and allowed addresses (held to
every rule a peer's are) and nothing to aim at: its endpoints are never taken,
and its relay is kept as the last resort. A tunnel mixing listen peers with
peers it aims at is refused, and a ring peer is never a listen peer. The tunnel
script points a listen peer nowhere and opens the session's listen port to UDP
over IPv4 on eth0 from any source, once for however many listen peers, in
chains the re-aiming never flushes; WireGuard answers only a handshake made
with a configured peer's key and learns the peer's address from it. The walk
never pokes, aims or punches for it: it waits for the peer's handshake (the
handshake time, not an endpoint alone), however late it comes, checks the path
with the full-size ping, and reports it ``inbound`` at the address it came
from, only once a ping came back over it (never on a stale handshake). One that
has not dialled in within its attempt, or whose dial-in is too narrow, moves to
its relay, and is then walked and reported as any relayed peer; a too-narrow
dial-in that WireGuard roams back to meanwhile is not taken as its path. With no
relay it is waited for until the deadline. Pings here go where WireGuard sends
them, to the endpoint it last heard the peer from. A peer no path reaches is no
path, one whose path is too narrow is ``path_too_narrow``, as for any peer.
Only the session's head takes one, and only in a container: a worker refuses
it, and a native tunnel (which lets in only the hosts it aims at) refuses it as
not capable. Such a head needs all of its tunnel ports reachable: four, from
its ``listen_port``.
"""

from __future__ import annotations

import dataclasses
import ipaddress
import json
import os
import re
import subprocess
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import hubwire
from mcgyvr.rig import pooled, protocol, session, sessionwire, tunnel
from tests import native_pool_fakes as native
from tests import rig_pool_fakes as fakes

KEY = "B" * 42 + "g="
OTHER_KEY = "C" * 42 + "w="
WORKER = "198.51.100.1"
OTHER_WORKER = "198.51.100.3"
#: Where the worker's NAT maps its dial-out, the address its handshake comes from:
#: a carrier-grade NAT's shared address, no LAN one.
DIALS_FROM = ("100.64.0.77", 40123)
RELAY_HOST = "203.0.113.50"
RELAY: dict[str, Any] = {"host": RELAY_HOST, "port": 3478, "ticket": "T" * 30}
HUB_HEAD = (hubwire.FEATURE_HUB_HEAD,)
SessionCode = sessionwire.SessionCode
OWN = (
    ipaddress.IPv4Interface("192.0.2.10/24"),
    ipaddress.IPv4Interface("203.0.113.2/24"),
)


def _peer(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "rig_id": "rig-worker",
        "public_key": KEY,
        "endpoints": [],
        "allowed_ips": [f"{WORKER}/32"],
        "keepalive_s": 25,
        "listen": True,
    }
    body.update(changes)
    return body


def _up_body(*peers: dict[str, Any], **changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "session_id": "s1",
        "address": f"{fakes.SELF}/24",
        "listen_port": 51820,
        "peers": list(peers) or [_peer()],
    }
    body.update(changes)
    return body


def _read(body: dict[str, Any], features: Sequence[str]) -> sessionwire.TunnelUp:
    envelope = protocol.decode(
        json.dumps({"v": 1, "type": "tunnel_up", "id": "t1", "body": body})
    )
    return sessionwire.read_tunnel_up(envelope, features=features)


def _plan(*peers: dict[str, Any]) -> tunnel.TunnelPlan:
    return tunnel.plan(_read(_up_body(*peers), HUB_HEAD), listen_port=51820, own=OWN)


# --- the plan --------------------------------------------------------------------


def test_a_listen_peer_is_planned_with_its_key_and_its_addresses_alone() -> None:
    plan = _plan(_peer())
    (peer,) = plan.peers
    assert peer.listen is True
    assert (peer.candidates, peer.relay, peer.ring) == ((), None, None)
    assert peer.allowed == (ipaddress.IPv4Network(f"{WORKER}/32"),)
    assert peer.tunnel_host == ipaddress.IPv4Address(WORKER)
    # the session's own port, the one it was prepared on and the hub was told
    assert plan.listen_port == 51820
    assert plan.script_args() == [
        f"{fakes.SELF}/24",
        "51820",
        KEY,
        tunnel.LISTEN_HOST,
        "0",
        "25",
        f"{WORKER}/32",
    ]


def test_a_listen_peers_endpoints_are_never_taken_and_its_relay_is_kept() -> None:
    endpoints = [{"host": "192.0.2.20", "port": 51820, "kind": "lan"}]
    (peer,) = _plan(_peer(endpoints=endpoints, relay=RELAY)).peers
    assert peer.candidates == ()
    assert peer.relay is not None
    assert str(peer.relay.host) == RELAY["host"]
    # still nothing to aim at in the tunnel script: the relay is taken by the walk
    assert _plan(_peer(endpoints=endpoints, relay=RELAY)).script_args()[3:5] == [
        tunnel.LISTEN_HOST,
        "0",
    ]
    # a relay this rig may not aim at is dropped, as any peer's is
    (mine,) = _plan(_peer(relay={**RELAY, "host": "192.0.2.10"})).peers
    assert mine.relay is None


def test_the_keepalive_the_hub_names_is_the_one_a_listen_peer_keeps() -> None:
    (peer,) = _plan(_peer(keepalive_s=0)).peers
    assert peer.keepalive_s == 0
    assert _plan(_peer(keepalive_s=0)).script_args()[5] == "0"


@pytest.mark.parametrize(
    ("allowed", "why"),
    [
        ("10.9.9.1/32", "an allowed address outside the tunnel"),
        (f"{fakes.SELF}/32", "allowed this rig's own address"),
    ],
)
def test_a_listen_peers_allowed_addresses_are_held_to_every_peers_rules(
    allowed: str, why: str
) -> None:
    with pytest.raises(tunnel.RefusedError, match=why):
        _plan(_peer(allowed_ips=[allowed]))


def test_two_listen_peers_may_not_share_an_address() -> None:
    with pytest.raises(tunnel.RefusedError, match="allowed another peer's address"):
        _plan(
            _peer(allowed_ips=["198.51.100.0/31"]),
            _peer(rig_id="rig-other", public_key=OTHER_KEY),
        )


def test_a_ring_peer_is_never_planned_as_a_listen_peer() -> None:
    # the reader refuses the pair on the wire ...
    ring = {"dial_ports": [50052]}
    with pytest.raises(protocol.ProtocolError, match=r"peers\.listen"):
        _read(_up_body(_peer(ring=ring)), HUB_HEAD)
    # ... and the planner refuses it too, whoever built the request
    needed = _peer(rig_id="rig-other", public_key=OTHER_KEY)
    needed["allowed_ips"] = [f"{OTHER_WORKER}/32"]
    up = _read(_up_body(_peer(), needed), HUB_HEAD)
    link = sessionwire.RingLink(dial_ports=(50052,), accept_ports=())
    both = dataclasses.replace(
        up, peers=(dataclasses.replace(up.peers[0], ring=link), up.peers[1])
    )
    with pytest.raises(tunnel.RefusedError, match="a ring peer cannot be a listen"):
        tunnel.plan(both, listen_port=51820, own=OWN)


def test_a_tunnel_mixing_listen_peers_with_peers_it_aims_at_is_refused() -> None:
    lan = [{"host": "192.0.2.20", "port": 51820, "kind": "lan"}]
    plain = _peer(
        rig_id="rig-plain",
        public_key=OTHER_KEY,
        endpoints=lan,
        allowed_ips=[f"{OTHER_WORKER}/32"],
        listen=False,
    )
    ring = {**plain, "ring": {"dial_ports": [50052]}}
    for other in (plain, ring):
        with pytest.raises(tunnel.RefusedError, match="listen peers beside") as got:
            _plan(_peer(), other)
        assert got.value.code == protocol.ErrorCode.BAD_MESSAGE


# --- without the feature, nothing changes --------------------------------------


def test_no_rig_names_the_hub_head_feature_yet() -> None:
    share = fakes.sharing(None, ring_links=True, port_forward=True)
    named = session.named_features(share, session.rig_builds(share))
    assert hubwire.FEATURE_HUB_HEAD not in named
    assert hubwire.FEATURE_HUB_HEAD not in session.FEATURES
    assert hubwire.FEATURE_HUB_HEAD not in session.NATIVE_FEATURES


def test_the_offer_names_the_features_the_tunnel_is_read_by() -> None:
    for changes in ({}, {"port_forward": True}, {"ring_links": True}):
        share = fakes.sharing(None, roles=("worker",), **changes)
        offered = session.offer(
            share, fakes.inventory(Path(".")), (), (), fakes.report()
        )
        assert offered.features == session.named_features(
            share, session.rig_builds(share)
        )
    # a rig that lends nothing names the hitchhike units alone, and has no
    # session whose frames could be read by any feature
    idle = fakes.sharing(None, enabled=False)
    offered = session.offer(idle, fakes.inventory(Path(".")), (), (), fakes.report())
    assert offered.features == (session.HITCHHIKE_FEATURE,)


def test_a_head_that_answers_dial_ins_needs_its_four_tunnel_ports_reachable() -> None:
    from mcgyvr.rig import sharing

    assert fakes.sharing(None).tunnel_ports() == range(51820, 51824)
    assert sharing.TUNNEL_PORTS == session.MAX_LIVE_SESSIONS == 4


@pytest.mark.parametrize("mark", [True, False, None])
def test_without_the_feature_a_marked_peer_is_planned_as_the_same_peer_unmarked(
    mark: bool | None,
) -> None:
    lan = [{"host": "192.0.2.20", "port": 51820, "kind": "lan"}]
    marked = _up_body(_peer(endpoints=lan, listen=mark))
    plain = _up_body(_peer(endpoints=lan))
    del plain["peers"][0]["listen"]
    share = fakes.sharing(None)
    features = session.named_features(share, session.rig_builds(share))
    assert _read(marked, features) == _read(plain, ())
    one = tunnel.plan(_read(marked, features), listen_port=51820, own=OWN)
    other = tunnel.plan(_read(plain, ()), listen_port=51820, own=OWN)
    assert one == other
    assert one.script_args() == other.script_args()
    assert tunnel.LISTEN_HOST not in one.script_args()
    # a marked peer with nothing to aim at is refused, as an unmarked one is
    with pytest.raises(tunnel.RefusedError, match="no endpoint or relay"):
        tunnel.plan(_read(_up_body(_peer()), features), listen_port=51820, own=OWN)


# --- the tunnel script -------------------------------------------------------------


def _stubs(folder: Path) -> dict[str, str]:
    log = folder / "calls.log"
    for name in ("nft", "wg", "ip"):
        stub = folder / name
        body = f'echo "{name} $*" >> "{log}"\n'
        if name == "nft":
            body += f'cat >> "{folder}/nft.rules"\n'
        stub.write_text("#!/bin/sh\n" + body)
        stub.chmod(0o755)
    return {"PATH": f"{folder}:{os.environ['PATH']}"}


def _run(folder: Path, script: str, *args: str) -> tuple[list[str], list[str]]:
    subprocess.run(
        ["sh", "-c", script, "mcgyvr", *args],
        env=_stubs(folder),
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    calls = (folder / "calls.log").read_text().splitlines()
    rules = (folder / "nft.rules").read_text().splitlines()
    return calls, [" ".join(line.split()) for line in rules if line.strip()]


def test_the_tunnel_lets_the_listen_port_in_from_anywhere_once_and_aims_nowhere(
    tmp_path: Path,
) -> None:
    plan = _plan(
        _peer(relay=RELAY),
        _peer(
            rig_id="rig-other", public_key=OTHER_KEY, allowed_ips=["198.51.100.3/32"]
        ),
    )
    calls, rules = _run(tmp_path, pooled.TUNNEL_SCRIPT, *plan.script_args())
    # nothing is aimed at, so the wg chains stay empty
    assert [r for r in rules if " wg_in " in r or " wg_out " in r] == []
    # the listen port, IPv4 from and to any address, once for both listen peers
    eth0 = [r for r in rules if "eth0" in r and " wg_" not in r]
    assert eth0 == [
        "add rule inet mcgyvr input iifname eth0 meta nfproto ipv4 "
        "udp dport 51820 accept",
        "add rule inet mcgyvr output oifname eth0 meta nfproto ipv4 "
        "udp sport 51820 accept",
    ]
    # every accept but those two names an address, and nothing else is opened
    for rule in rules:
        if rule.endswith("accept") and rule not in eth0:
            assert re.search(r"ip [sd]addr \d", rule), rule
    # in the same transaction as the rest, before WireGuard takes the port
    assert calls[0] == "nft -f -"
    assert calls[1] == "wg set wg0 listen-port 51820"
    assert (
        f"wg set wg0 peer {KEY} allowed-ips {WORKER}/32 persistent-keepalive 25"
        in calls
    )
    assert (
        f"wg set wg0 peer {OTHER_KEY} allowed-ips 198.51.100.3/32 "
        "persistent-keepalive 25" in calls
    )
    assert not any(f"endpoint {tunnel.LISTEN_HOST}" in call for call in calls)


def test_the_re_aiming_never_flushes_the_chains_the_listen_port_is_opened_in() -> None:
    flushed = re.findall(r"flush chain inet mcgyvr (\w+)", pooled.PATH_SCRIPT)
    assert set(flushed) == {"wg_in", "wg_out"}
    assert "input" not in flushed and "output" not in flushed


def test_a_tunnel_with_no_listen_peer_opens_no_port_to_any_address(
    tmp_path: Path,
) -> None:
    lan = [{"host": "192.0.2.20", "port": 51820, "kind": "lan"}]
    plan = _plan(
        _peer(endpoints=lan, listen=False),
        _peer(
            rig_id="rig-relayed",
            public_key=OTHER_KEY,
            allowed_ips=["198.51.100.3/32"],
            relay=RELAY,
            listen=False,
        ),
    )
    _, rules = _run(tmp_path, pooled.TUNNEL_SCRIPT, *plan.script_args())
    for rule in rules:
        if rule.endswith("accept"):
            assert re.search(r"ip [sd]addr \d", rule), rule


# --- the walk ---------------------------------------------------------------------


@pytest.fixture
def pool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[fakes.Pool]:
    named = session.named_features

    def with_hub_head(share: Any, builds: Any) -> tuple[str, ...]:
        return (*named(share, builds), hubwire.FEATURE_HUB_HEAD)

    monkeypatch.setattr(session, "named_features", with_hub_head)
    made = fakes.make_pool(tmp_path)
    # a ping goes where WireGuard sends it: to the endpoint it roamed to
    made.docker.ping_follows_endpoint = True
    yield made
    made.sessions.close()


def _scripts(pool: fakes.Pool, script: str) -> list[tuple[str, ...]]:
    return [args for _, s, args in pool.docker.scripts if s == script]


def _head(pool: fakes.Pool) -> None:
    fakes.prepared(pool, role="head")


def test_a_peer_that_dials_in_is_answered_and_reported_inbound(
    pool: fakes.Pool,
) -> None:
    pool.docker.dials_in = {KEY: DIALS_FROM}
    _head(pool)
    report = pool.up("t1", **_up_body(_peer(relay=RELAY)))
    (path,) = report["body"]["peers"]
    assert path["path"] == hubwire.TUNNEL_INBOUND_PATH == "inbound"
    host, port = DIALS_FROM
    assert path["endpoint"] == {"host": host, "port": port, "kind": "reflexive"}
    assert path["rtt_us"] == 512
    assert pool.sessions.state_of("s1") == ("tunnel_up", "head")
    # nothing was poked, aimed, punched or relayed for it
    assert all(args == () for args in _scripts(pool, pooled.PEERS_SCRIPT))
    assert _scripts(pool, pooled.PATH_SCRIPT) == []
    assert [p for p in pool.docker.python if p[1] == "start"] == []
    assert pool.relayed == []
    assert pool.docker.aims == {}
    pool.settle()
    (frame,) = pool.box.of_type("peer_rtt")
    assert frame["body"]["samples"] == [{"rig_id": "rig-worker", "rtt_us": 512}]


def test_a_peer_that_dials_in_from_the_lan_is_reported_at_a_lan_endpoint(
    pool: fakes.Pool,
) -> None:
    pool.docker.dials_in = {KEY: ("192.0.2.44", 51820)}
    _head(pool)
    (path,) = pool.up("t1", **_up_body())["body"]["peers"]
    assert path["path"] == "inbound"
    assert path["endpoint"]["kind"] == "lan"


def test_the_head_reaches_the_worker_that_dialled_in_over_the_tunnel(
    pool: fakes.Pool,
) -> None:
    pool.docker.dials_in = {KEY: DIALS_FROM}
    _head(pool)
    pool.up("t1", **_up_body(address=f"{fakes.SELF}/24"))
    ack = pool.ask(
        "head_start",
        "h1",
        session_id="s1",
        model={"name": fakes.MODEL},
        ctx=4096,
        devices=[{"kind": "rpc", "host": WORKER, "port": 50052}],
        tensor_split=[1],
    )
    assert ack is not None and ack["type"] == "ack", ack
    pool.wait_for("session_status", "ready")
    (opened,) = _scripts(pool, pooled.OPEN_HEAD_SCRIPT)
    assert opened[0] == fakes.SELF and opened[-2:] == (WORKER, "50052")


def test_a_peer_that_dials_in_late_is_waited_for_and_its_relay_left_alone(
    pool: fakes.Pool,
) -> None:
    # the worker's handshake comes only at the sixth look: the head keeps waiting,
    # within its attempt, and never moves to the relay
    pool.docker.dials_in = {KEY: DIALS_FROM}
    pool.docker.dial_after = 5
    _head(pool)
    body = _up_body(_peer(relay=RELAY), attempt_s=10, connect_timeout_s=20)
    (path,) = pool.up("t1", **body)["body"]["peers"]
    assert path["path"] == "inbound"
    assert pool.docker.looks > 5
    assert pool.relayed == []
    assert _scripts(pool, pooled.PATH_SCRIPT) == []


def test_a_peer_with_no_relay_is_waited_for_past_its_attempt(
    pool: fakes.Pool,
) -> None:
    assert QUICK_ATTEMPT_S < 0.1
    pool.docker.dials_in = {KEY: DIALS_FROM}
    pool.docker.dial_after = 20
    _head(pool)
    body = _up_body(_peer(), connect_timeout_s=20)
    (path,) = pool.up("t1", **body)["body"]["peers"]
    assert path["path"] == "inbound"


def test_a_peer_whose_relay_will_not_bind_is_still_waited_for(
    pool: fakes.Pool,
) -> None:
    pool.relay_port = None
    pool.docker.dials_in = {KEY: DIALS_FROM}
    pool.docker.dial_after = 20
    _head(pool)
    body = _up_body(_peer(relay=RELAY), connect_timeout_s=20)
    (path,) = pool.up("t1", **body)["body"]["peers"]
    assert path["path"] == "inbound"
    assert len(pool.relayed) == 1


def test_an_endpoint_with_no_handshake_is_no_dial_in(pool: fakes.Pool) -> None:
    # WireGuard may show where an initiation came from before the handshake is
    # done: only the handshake time says the peer is there
    pool.docker.dials_in = {KEY: DIALS_FROM}
    pool.docker.dial_after = 10**9
    _head(pool)
    report = pool.up("t1", **_up_body(_peer(), connect_timeout_s=1))
    assert report["body"]["peers"] == [{"rig_id": "rig-worker", "path": "none"}]
    assert any(
        line.startswith(f"endpoint {KEY}\t{DIALS_FROM[0]}")
        for line in pool.docker._peers().splitlines()
    )


def test_a_peer_with_no_relay_that_never_dials_in_is_no_path_at_the_deadline(
    pool: fakes.Pool,
) -> None:
    _head(pool)
    report = pool.up("t1", **_up_body(_peer(), connect_timeout_s=1))
    assert report["body"]["peers"] == [{"rig_id": "rig-worker", "path": "none"}]
    pool.wait_for("session_status", "failed")
    (failed,) = pool.box.of_type("session_status")[-1:]
    assert failed["body"]["error_code"] == SessionCode.NO_PATH
    assert pool.relayed == []
    assert _scripts(pool, pooled.PATH_SCRIPT) == []


RELAYED = (RELAY_HOST, 40001)
#: The session's attempt when the hub names none: the quick timing's, far
#: shorter than the looks a late dial-in takes (``FakeDocker.dial_after``).
QUICK_ATTEMPT_S = fakes.quick_timing().attempt_s


def test_a_peer_that_does_not_dial_in_within_its_attempt_is_reached_on_its_relay(
    pool: fakes.Pool,
) -> None:
    pool.docker.answering = {RELAYED}
    _head(pool)
    body = _up_body(_peer(relay=RELAY), connect_timeout_s=10)
    (path,) = pool.up("t1", **body)["body"]["peers"]
    assert path["path"] == "relay"
    assert path["endpoint"] == {"host": RELAYED[0], "port": RELAYED[1], "kind": "relay"}
    (grant,) = pool.relayed
    assert grant.ticket == RELAY["ticket"]
    # from there it is walked as any relayed peer: aimed at the relay, and poked
    assert any(
        args[1:3] == (KEY, RELAYED[0]) for args in _scripts(pool, pooled.PATH_SCRIPT)
    )
    assert any(WORKER in args for args in _scripts(pool, pooled.PEERS_SCRIPT))
    # and it never punched
    assert [p for p in pool.docker.python if p[1] == "start"] == []


def test_a_peer_neither_dialling_in_nor_answering_on_its_relay_is_no_path(
    pool: fakes.Pool,
) -> None:
    pool.docker.answering = set()
    _head(pool)
    body = _up_body(_peer(relay=RELAY), connect_timeout_s=1)
    report = pool.up("t1", **body)
    assert report["body"]["peers"] == [{"rig_id": "rig-worker", "path": "none"}]
    pool.wait_for("session_status", "failed")
    (failed,) = pool.box.of_type("session_status")[-1:]
    assert failed["body"]["error_code"] == SessionCode.NO_PATH
    assert len(pool.relayed) == 1


def test_a_peer_that_dials_in_on_a_path_too_narrow_is_refused_as_too_narrow(
    pool: fakes.Pool,
) -> None:
    pool.docker.dials_in = {KEY: DIALS_FROM}
    pool.docker.narrow = {DIALS_FROM}
    _head(pool)
    answer = pool.ask("tunnel_up", "t1", **_up_body())
    assert answer is None
    pool.wait_for("error")
    (refused,) = pool.box.of_type("error")
    assert refused["body"]["code"] == SessionCode.PATH_TOO_NARROW
    assert "its dial-in answered a small ping" in refused["body"]["message"]
    assert any(f"{DIALS_FROM[0]}:{DIALS_FROM[1]}" in line for line in pool.logged)


def test_a_peer_that_dials_in_too_narrow_moves_to_its_relay(
    pool: fakes.Pool,
) -> None:
    pool.docker.dials_in = {KEY: DIALS_FROM}
    pool.docker.narrow = {DIALS_FROM}
    _head(pool)
    body = _up_body(_peer(relay=RELAY), attempt_s=5, connect_timeout_s=10)
    (path,) = pool.up("t1", **body)["body"]["peers"]
    assert path["path"] == "relay"
    assert len(pool.relayed) == 1


def test_a_dial_in_heard_again_after_the_move_to_the_relay_is_not_the_path(
    pool: fakes.Pool,
) -> None:
    # the dial-in is too narrow and the head moves to the relay; the worker has
    # not moved yet, so its next two packets still come direct and WireGuard
    # roams the head back there; then the worker is on the relay too
    pool.docker.dials_in = {KEY: DIALS_FROM}
    pool.docker.narrow = {DIALS_FROM}
    pool.docker.heard_once_aimed = {KEY: [DIALS_FROM, DIALS_FROM, RELAYED]}
    _head(pool)
    body = _up_body(_peer(relay=RELAY), attempt_s=5, connect_timeout_s=10)
    (path,) = pool.up("t1", **body)["body"]["peers"]
    assert path["path"] == "relay"
    assert path["endpoint"]["host"] == RELAY_HOST
    # the narrow dial-in was measured once, and named as the dial-in
    spent = [line for line in pool.logged if "small ping" in line]
    assert len(spent) == 1 and "its dial-in" in spent[0], spent
    assert f"{DIALS_FROM[0]}:{DIALS_FROM[1]}" in spent[0]


def test_a_too_narrow_relay_after_a_too_narrow_dial_in_names_each(
    pool: fakes.Pool,
) -> None:
    pool.docker.dials_in = {KEY: DIALS_FROM}
    pool.docker.narrow = {DIALS_FROM, RELAYED}
    _head(pool)
    body = _up_body(_peer(relay=RELAY), attempt_s=5, connect_timeout_s=10)
    assert pool.ask("tunnel_up", "t1", **body) is None
    pool.wait_for("error")
    (refused,) = pool.box.of_type("error")
    assert refused["body"]["code"] == SessionCode.PATH_TOO_NARROW
    assert refused["body"]["message"].startswith("its relay answered a small ping")
    spent = [line for line in pool.logged if "small ping" in line]
    assert len(spent) == 2
    assert "its dial-in" in spent[0] and f"{DIALS_FROM[0]}:" in spent[0]
    assert "its relay" in spent[1] and f"{RELAY_HOST}:" in spent[1]


def test_a_too_narrow_dial_in_after_the_move_to_the_relay_leaves_it_on_the_relay(
    pool: fakes.Pool,
) -> None:
    # no dial-in within the attempt, so the head binds its relay; then the worker's
    # direct dial-in lands, too narrow; then the relay carries it
    pool.docker.narrow = {DIALS_FROM}
    pool.docker.heard_once_aimed = {KEY: [DIALS_FROM, RELAYED]}
    _head(pool)
    body = _up_body(_peer(relay=RELAY), connect_timeout_s=10)
    (path,) = pool.up("t1", **body)["body"]["peers"]
    assert path["path"] == "relay"
    spent = [line for line in pool.logged if "small ping" in line]
    assert len(spent) == 1 and "its dial-in" in spent[0], spent
    assert f"{DIALS_FROM[0]}:{DIALS_FROM[1]}" in spent[0]


def test_a_too_narrow_dial_in_after_a_relay_that_would_not_bind_is_too_narrow(
    pool: fakes.Pool,
) -> None:
    # no dial-in within the attempt, and the relay will not bind, so the head
    # waits on; then the dial-in lands, too narrow, with nowhere left to go
    pool.relay_port = None
    pool.docker.dials_in = {KEY: DIALS_FROM}
    pool.docker.dial_after = 20
    pool.docker.narrow = {DIALS_FROM}
    _head(pool)
    body = _up_body(_peer(relay=RELAY), connect_timeout_s=20)
    assert pool.ask("tunnel_up", "t1", **body) is None
    pool.wait_for("error")
    (refused,) = pool.box.of_type("error")
    assert refused["body"]["code"] == SessionCode.PATH_TOO_NARROW
    assert refused["body"]["message"].startswith("its dial-in answered a small ping")
    assert len(pool.relayed) == 1


def test_a_peer_with_no_tunnel_host_to_ping_is_taken_on_its_handshake(
    pool: fakes.Pool,
) -> None:
    # allowed a network, no single address: the plan takes it, and there is
    # nothing the walk can ping, so its handshake is all that says it came
    pool.docker.dials_in = {KEY: DIALS_FROM}
    _head(pool)
    (planned,) = _plan(_peer(allowed_ips=["198.51.100.4/30"])).peers
    assert planned.tunnel_host is None
    body = _up_body(_peer(allowed_ips=["198.51.100.4/30"]), connect_timeout_s=10)
    (path,) = pool.up("t1", **body)["body"]["peers"]
    assert path["path"] == "inbound"
    assert "rtt_us" not in path
    assert _scripts(pool, pooled.PING_SCRIPT) == []


def test_a_stale_handshake_is_not_taken_as_the_relay_answering(
    pool: fakes.Pool,
) -> None:
    # the head moves to the relay just as the worker's direct handshake lands:
    # WireGuard shows the relay it was pointed at and a handshake time, but the
    # relay carries nothing; the worker's next packet roams the head back direct
    pool.docker.answering = {DIALS_FROM}
    pool.docker.heard_once_aimed = {KEY: [RELAYED, RELAYED, DIALS_FROM]}
    _head(pool)
    body = _up_body(_peer(relay=RELAY), connect_timeout_s=10)
    (path,) = pool.up("t1", **body)["body"]["peers"]
    assert len(pool.relayed) == 1
    assert path["path"] == "inbound"
    assert path["endpoint"]["host"] == DIALS_FROM[0]


def test_a_head_refuses_listen_peers_beside_a_peer_it_aims_at(
    pool: fakes.Pool,
) -> None:
    _head(pool)
    lan = [{"host": "192.0.2.20", "port": 51820, "kind": "lan"}]
    plain = _peer(
        rig_id="rig-plain",
        public_key=OTHER_KEY,
        endpoints=lan,
        allowed_ips=[f"{OTHER_WORKER}/32"],
        listen=False,
    )
    answer = pool.ask("tunnel_up", "t1", **_up_body(_peer(), plain))
    assert answer is not None and answer["type"] == "error"
    assert answer["body"]["code"] == protocol.ErrorCode.BAD_MESSAGE
    assert "listen peers beside a peer this rig aims at" in answer["body"]["message"]
    assert _scripts(pool, pooled.TUNNEL_SCRIPT) == []


def _hub_head_by_port_forward(monkeypatch: pytest.MonkeyPatch) -> None:
    """Name ``hub_head`` exactly when the settings allow the port forward: a
    setting that stands in for the owner's switch the feature will have."""
    named = session.named_features

    def by_setting(share: Any, builds: Any) -> tuple[str, ...]:
        extra = (hubwire.FEATURE_HUB_HEAD,) if share.port_forward else ()
        return (*named(share, builds), *extra)

    monkeypatch.setattr(session, "named_features", by_setting)


@pytest.mark.parametrize(("before", "after"), [(True, False), (False, True)])
def test_a_tunnel_is_read_by_the_features_its_session_was_prepared_with(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, before: bool, after: bool
) -> None:
    _hub_head_by_port_forward(monkeypatch)
    pool = fakes.make_pool(tmp_path, port_forward=before)
    try:
        pool.docker.dials_in = {KEY: DIALS_FROM}
        _head(pool)
        # the setting changes after the hub planned the session
        later = fakes.sharing(tmp_path, port_forward=after)
        pool.sessions.machine = dataclasses.replace(
            pool.sessions.machine, sharing=lambda: later
        )
        answer = pool.ask("tunnel_up", "t1", **_up_body())
        if before:
            assert answer is None
            (path,) = pool.report("t1")["body"]["peers"]
            assert path["path"] == "inbound"
        else:
            # read without the feature: a peer with nothing to aim at, refused
            assert answer is not None and answer["type"] == "error", answer
            assert "no endpoint or relay" in answer["body"]["message"]
    finally:
        pool.sessions.close()


def test_a_worker_refuses_a_peer_that_would_dial_in(pool: fakes.Pool) -> None:
    fakes.prepared(pool, role="worker")
    answer = pool.ask("tunnel_up", "t1", **_up_body())
    assert answer is not None and answer["type"] == "error"
    assert answer["body"]["code"] == protocol.ErrorCode.BAD_MESSAGE
    assert (
        "a listen peer, and this rig is not the session's head"
        in (answer["body"]["message"])
    )
    assert _scripts(pool, pooled.TUNNEL_SCRIPT) == []


def test_without_the_feature_a_head_aims_at_a_marked_peer_as_before(
    tmp_path: Path,
) -> None:
    pool = fakes.make_pool(tmp_path)
    try:
        _head(pool)
        lan = [{"host": "192.0.2.20", "port": 51820, "kind": "lan"}]
        report = pool.up("t1", **_up_body(_peer(endpoints=lan)))
        (path,) = report["body"]["peers"]
        assert path["path"] == "lan"
        (up,) = _scripts(pool, pooled.TUNNEL_SCRIPT)
        assert tunnel.LISTEN_HOST not in up and "192.0.2.20" in up
    finally:
        pool.sessions.close()


def test_a_native_head_refuses_a_peer_that_would_dial_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    named = session.named_features
    monkeypatch.setattr(
        session,
        "named_features",
        lambda share, builds: (*named(share, builds), hubwire.FEATURE_HUB_HEAD),
    )
    rig = native.make_native_pool(tmp_path, monkeypatch)
    try:
        pool = rig.pool
        assert pool.ask("session_prepare", "p1", session_id="s1", role="head") is None
        pool.wait_for("session_prepared")
        answer = pool.ask("tunnel_up", "t1", **_up_body())
        assert answer is not None and answer["type"] == "error"
        assert answer["body"]["code"] == SessionCode.NOT_CAPABLE
        assert "native tunnel" in answer["body"]["message"]
        assert "up" not in rig.verbs()
    finally:
        rig.pool.sessions.close()
        rig.echo.close()
