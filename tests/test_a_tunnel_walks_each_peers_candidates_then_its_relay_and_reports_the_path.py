"""A tunnel walks each peer's candidates, then its relay, and reports the path.

Two rigs in different homes reach each other only through their NATs. A
session the hub prepares with a binding token has the tunnel's own port —
before WireGuard takes it — ask the hub's responders where it is seen from,
and keep asking until the tunnel comes up, so the address the hub hands the
peers is the one WireGuard's packets will leave by; the answer to
``session_prepare`` carries the round trip. ``tunnel_up`` then has each rig
point WireGuard at each peer's candidates in the hub's order, a time per
candidate (both rigs at once: each side's handshakes open its own NAT for the
other's), until a handshake completes; a peer no candidate reaches is
pointed at its relay, once bound; ``tunnel_report`` answers with each peer's
path (``lan``, ``direct``, ``relay`` or ``none``), the endpoint WireGuard
uses and the round trip. A peer no path reaches fails the session as
``no_path``.

The table stays as tight as before: while a candidate is tried, only its
address may reach the port; once a path is confirmed, only that endpoint,
port and all; the responders only while the port asks them. An address the
hub must not aim this rig at — loopback, link-local, multicast, this
machine's own, one inside the tunnel, a name — is never tried, nor a relay
named by a host name.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes
from tests.rig_pool_fakes import Pool, make_pool

TOKEN = "00112233445566778899aabbccddeeff"
STUN = "203.0.113.9"
RELAY = "203.0.113.50"
#: Public addresses, written as numbers so that no real machine is named.
REFLEXIVE = str(ipaddress.IPv4Address(2**31 + 7))
OTHER = str(ipaddress.IPv4Address(2**31 + 8))


@pytest.fixture
def pool(tmp_path: Path) -> Iterator[Pool]:
    made = make_pool(tmp_path)
    yield made
    made.sessions.close()


def _prepare(pool: Pool, role: str = "worker", **traversal: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"session_id": "s1", "role": role}
    if traversal:
        body["traversal"] = traversal
    assert pool.ask("session_prepare", "p1", **body) is None
    pool.wait_for("session_prepared")
    found: dict[str, Any] = pool.box.of_type("session_prepared")[0]
    return found


def _traversal() -> dict[str, Any]:
    return {"token": TOKEN, "stun": [{"host": STUN, "port": 3478, "kind": "stun"}]}


def _body(endpoints: list[dict[str, Any]], **peer: Any) -> dict[str, Any]:
    body = fakes.tunnel_up_body()
    body["peers"][0]["endpoints"] = endpoints
    body["peers"][0].update(peer)
    return body


def _lan(host: str = fakes.PEER_ADDRESS, port: int = 51820) -> dict[str, Any]:
    return {"host": host, "port": port, "kind": "lan"}


def _reflexive(host: str = REFLEXIVE, port: int = 40000) -> dict[str, Any]:
    return {"host": host, "port": port, "kind": "reflexive"}


def _scripts(pool: Pool, name: str) -> list[tuple[str, ...]]:
    from mcgyvr.sandbox import pooled

    script = getattr(pooled, name)
    return [args for _, s, args in pool.docker.scripts if s == script]


def test_a_traversal_prepare_asks_the_responders_from_the_tunnels_port(
    pool: Pool,
) -> None:
    prepared = _prepare(pool, **_traversal())
    assert prepared["body"]["stun_rtt_us"] == 1500
    assert _scripts(pool, "STUN_SCRIPT") == [("51820", STUN, "3478")]
    ran = [call for call in pool.docker.python if call[1] == "run"]
    started = [call for call in pool.docker.python if call[1] == "start"]
    assert [call[2][:3] for call in ran] == [("stun", "51820", TOKEN)]
    assert ran[0][2][-2:] == (STUN, "3478")
    assert [call[2][:3] for call in started] == [("keep", "51820", TOKEN)]
    assert started[0][2][-2:] == (STUN, "3478")


def test_a_prepare_without_traversal_asks_no_responder(pool: Pool) -> None:
    prepared = _prepare(pool)
    assert "stun_rtt_us" not in prepared["body"]
    assert _scripts(pool, "STUN_SCRIPT") == [] and pool.docker.python == []


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "0.0.0.0", fakes.LAN_ADDRESS, "stun.invalid"],
)
def test_a_responder_the_rig_must_not_reach_is_never_asked(
    pool: Pool, host: str
) -> None:
    prepared = _prepare(
        pool, token=TOKEN, stun=[{"host": host, "port": 3478, "kind": "stun"}]
    )
    assert "stun_rtt_us" not in prepared["body"]
    assert _scripts(pool, "STUN_SCRIPT") == [] and pool.docker.python == []


def test_a_lan_peer_is_reached_on_its_lan_address_and_reported_so(pool: Pool) -> None:
    _prepare(pool, **_traversal())
    report = pool.up("t1", **_body([_lan(), _reflexive()]))
    (peer,) = report["body"]["peers"]
    assert peer["rig_id"] == "rig-peer" and peer["path"] == "lan"
    assert peer["endpoint"] == _lan()
    assert peer["rtt_us"] == 512
    assert pool.sessions.state_of("s1") == ("tunnel_up", "worker")
    up = _scripts(pool, "TUNNEL_SCRIPT")
    assert up and up[0][2:4] == (fakes.PEER_KEY, fakes.PEER_ADDRESS)
    tight = _scripts(pool, "PATH_SCRIPT")[-1]
    assert tight == ("51820", fakes.PEER_KEY, fakes.PEER_ADDRESS, "51820", "exact", "0")


def test_a_peer_behind_a_nat_is_reached_at_its_reflexive_address_after_its_lan(
    pool: Pool,
) -> None:
    pool.docker.answering = {(REFLEXIVE, 40000)}
    _prepare(pool, **_traversal())
    report = pool.up("t1", **_body([_lan(), _reflexive()]))
    (peer,) = report["body"]["peers"]
    assert peer["path"] == "direct" and peer["endpoint"] == _reflexive()
    aimed = [args for args in _scripts(pool, "PATH_SCRIPT") if args[-1] == "1"]
    assert aimed and aimed[0][2:5] == (REFLEXIVE, "40000", "host")
    tight = _scripts(pool, "PATH_SCRIPT")[-1]
    assert tight == ("51820", fakes.PEER_KEY, REFLEXIVE, "40000", "exact", "0")
    assert pool.relayed == []


def test_a_peer_whose_nat_moved_the_port_is_held_to_where_it_answered(
    pool: Pool,
) -> None:
    pool.docker.answering = {(REFLEXIVE, 40000)}
    pool.docker.roams = {(REFLEXIVE, 40000): (REFLEXIVE, 40999)}
    _prepare(pool, **_traversal())
    report = pool.up("t1", **_body([_reflexive()]))
    (peer,) = report["body"]["peers"]
    assert peer["path"] == "direct"
    assert peer["endpoint"] == {"host": REFLEXIVE, "port": 40999, "kind": "reflexive"}
    tight = _scripts(pool, "PATH_SCRIPT")[-1]
    assert tight == ("51820", fakes.PEER_KEY, REFLEXIVE, "40999", "exact", "0")


def test_a_peer_no_candidate_reaches_is_reached_through_its_relay(pool: Pool) -> None:
    pool.docker.answering = {(RELAY, 40001)}
    _prepare(pool, **_traversal())
    grant = {"host": RELAY, "port": 3478, "ticket": "T" * 30}
    report = pool.up("t1", **_body([_lan(), _reflexive()], relay=grant))
    (peer,) = report["body"]["peers"]
    assert peer["path"] == "relay"
    assert peer["endpoint"] == {"host": RELAY, "port": 40001, "kind": "relay"}
    (bound,) = pool.relayed
    assert (bound.host, bound.port, bound.ticket) == (RELAY, 3478, "T" * 30)
    tight = _scripts(pool, "PATH_SCRIPT")[-1]
    assert tight == ("51820", fakes.PEER_KEY, RELAY, "40001", "exact", "0")


def test_a_peer_no_path_reaches_fails_the_session_as_no_path(pool: Pool) -> None:
    pool.docker.answering = set()
    pool.relay_port = None
    _prepare(pool, **_traversal())
    grant = {"host": RELAY, "port": 3478, "ticket": "T" * 30}
    report = pool.up("t1", **_body([_reflexive()], relay=grant))
    assert report["body"]["peers"] == [{"rig_id": "rig-peer", "path": "none"}]
    pool.wait_for("session_status", "failed")
    failed = pool.box.of_type("session_status")[-1]["body"]
    assert failed["error_code"] == "no_path"
    assert pool.docker.of_session("s1") == []


@pytest.mark.parametrize(
    "hostile",
    [
        "127.0.0.1",
        "0.0.0.0",
        fakes.LAN_ADDRESS,
        fakes.PEER,
        "peer.invalid",
        "2001:db8::1",
    ],
)
def test_an_address_the_rig_must_not_be_aimed_at_is_never_tried(
    pool: Pool, hostile: str
) -> None:
    pool.docker.answering = {(REFLEXIVE, 40000)}
    _prepare(pool, **_traversal())
    bad = {"host": hostile, "port": 51820, "kind": "reflexive"}
    report = pool.up("t1", **_body([bad, _reflexive()]))
    assert report["body"]["peers"][0]["path"] == "direct"
    for args in _scripts(pool, "TUNNEL_SCRIPT") + _scripts(pool, "PATH_SCRIPT"):
        assert hostile not in args


def test_a_relay_named_by_a_host_name_is_never_bound(pool: Pool) -> None:
    pool.docker.answering = set()
    _prepare(pool, **_traversal())
    grant = {"host": "relay.invalid", "port": 3478, "ticket": "T" * 30}
    report = pool.up("t1", **_body([_reflexive()], relay=grant))
    assert report["body"]["peers"][0]["path"] == "none"
    assert pool.relayed == []


def test_a_peer_with_nothing_to_try_is_refused_at_once(pool: Pool) -> None:
    _prepare(pool, **_traversal())
    refused = pool.ask("tunnel_up", "t1", **_body([_lan("127.0.0.1")]))
    assert refused is not None and refused["body"]["code"] == "tunnel_failed"
    pool.settle()
    assert _scripts(pool, "TUNNEL_SCRIPT") == []


def test_the_same_tunnel_up_again_is_answered_the_same_report(pool: Pool) -> None:
    _prepare(pool, **_traversal())
    first = pool.up("t1", **_body([_lan()]))
    again = pool.ask("tunnel_up", "t2", **_body([_lan()]))
    assert again is not None and again["type"] == "tunnel_report"
    assert again["re"] == "t2" and again["body"] == first["body"]
    other = pool.ask("tunnel_up", "t3", **_body([_reflexive()]))
    assert other is not None and other["body"]["code"] == "bad_message"
    assert len(_scripts(pool, "TUNNEL_SCRIPT")) == 1


def test_an_address_the_owner_names_outside_the_lan_is_offered_as_public(
    tmp_path: Path,
) -> None:
    from mcgyvr.rig import inventory, session

    made = make_pool(tmp_path, endpoints=(fakes.LAN_ADDRESS, REFLEXIVE))
    try:
        prepared = _prepare(made)
        assert prepared["body"]["endpoints"] == [
            {"host": fakes.LAN_ADDRESS, "port": 51820, "kind": "lan"},
            {"host": REFLEXIVE, "port": 51820, "kind": "public"},
        ]
        share = made.sessions.machine.sharing()
        held = inventory.Inventory(folder=None, models=(), files={})
        offer = session.offer(share, held, share.endpoints, ())
        assert offer is not None
        assert [kind for _, _, kind in offer.endpoints] == ["lan", "public"]
    finally:
        made.sessions.close()
