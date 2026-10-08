"""A path that loses full-size packets is not taken.

A WireGuard handshake and a ping are small packets; a model's weights cross
the tunnel in packets as large as its interface carries. A path whose MTU is
smaller than the tunnel was sized for passes the first and loses the second
without a word, and a session brought up over it stalls at its first load.
So when a handshake confirms a path, the tunnel sends the peer a ping the
size of its interface's MTU, in the step that measures the round trip: a
path that answers the small ping and none of the full-size ones cannot carry
the load. A candidate found so is spent like one that never answered — the
walk goes on to the next, then to the relay — and the agent's log says why.
The handshake made on the spent candidate still stands, so what comes after
it is taken only once a full-size ping crosses it. A relay found so ends the
walk at once, as a relay that cannot be bound does: nothing comes after it,
and the session fails as ``path_too_narrow``, saying what was lost. That code
is for the peer whose last path was found so, and for no other: the rig
answers the hub's ``tunnel_up`` with an ``error`` of that code in place of a
report (a report saying ``none`` is what the hub reads as ``no_path``), and
its ``session_status`` says ``failed`` with the same code. A peer whose last
path never answered stays ``no_path``, a narrow candidate before it or not.
A path that carries both is taken as before, and a peer that answers no ping
at all is not judged by this: the watch of a session's peers is what finds it.
"""

from __future__ import annotations

import ipaddress
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes
from tests.rig_pool_fakes import Pool, make_pool

TOKEN = "00112233445566778899aabbccddeeff"
STUN = "203.0.113.9"
RELAY = "203.0.113.50"
#: A public address, written as a number so that no real machine is named.
REFLEXIVE = str(ipaddress.IPv4Address(2**31 + 7))
LAN = {"host": fakes.PEER_ADDRESS, "port": 51820, "kind": "lan"}
DIRECT = {"host": REFLEXIVE, "port": 40000, "kind": "reflexive"}
GRANT = {"host": RELAY, "port": 3478, "ticket": "T" * 30}


@pytest.fixture
def pool(tmp_path: Path) -> Iterator[Pool]:
    made = make_pool(tmp_path)
    yield made
    made.sessions.close()


def _prepare(pool: Pool) -> None:
    traversal = {"token": TOKEN, "stun": [{"host": STUN, "port": 3478, "kind": "stun"}]}
    body = {"session_id": "s1", "role": "worker", "traversal": traversal}
    assert pool.ask("session_prepare", "p1", **body) is None
    pool.wait_for("session_prepared")


def _body(endpoints: list[dict[str, Any]], **peer: Any) -> dict[str, Any]:
    body = fakes.tunnel_up_body()
    body["peers"][0]["endpoints"] = endpoints
    body["peers"][0].update(peer)
    return body


def _why(pool: Pool) -> list[str]:
    return [line for line in pool.logged if "full-size" in line]


def test_a_candidate_that_loses_full_size_packets_is_spent_and_the_next_is_taken(
    pool: Pool,
) -> None:
    pool.docker.narrow = {(fakes.PEER_ADDRESS, 51820)}
    _prepare(pool)
    report = pool.up("t1", **_body([LAN, DIRECT]))
    (peer,) = report["body"]["peers"]
    assert peer["path"] == "direct" and peer["endpoint"] == DIRECT
    assert peer["rtt_us"] == 512
    assert pool.sessions.state_of("s1") == ("tunnel_up", "worker")
    (said,) = _why(pool)
    assert "s1" in said and "rig-peer" in said and "1172" in said
    assert f"{fakes.PEER_ADDRESS}:51820" in said


def test_what_follows_a_spent_candidate_is_taken_only_once_a_full_size_ping_crosses(
    pool: Pool,
) -> None:
    # The handshake made on the LAN candidate still stands when the tunnel is
    # pointed at the next one, where nothing answers: it is not a path.
    pool.docker.narrow = {(fakes.PEER_ADDRESS, 51820)}
    pool.docker.answering = {(fakes.PEER_ADDRESS, 51820), (RELAY, 40001)}
    _prepare(pool)
    report = pool.up("t1", **_body([LAN, DIRECT], relay=GRANT))
    (peer,) = report["body"]["peers"]
    assert peer["path"] == "relay"
    assert peer["endpoint"] == {"host": RELAY, "port": 40001, "kind": "relay"}
    assert len(_why(pool)) == 1


def _refused(pool: Pool, message_id: str = "t1") -> list[dict[str, Any]]:
    return [f for f in pool.box.of_type("error") if f.get("re") == message_id]


def test_a_relay_that_loses_full_size_packets_fails_the_session_at_once(
    pool: Pool,
) -> None:
    pool.docker.narrow = {(RELAY, 40001)}
    pool.docker.answering = {(RELAY, 40001)}
    _prepare(pool)
    began = time.monotonic()
    assert pool.ask("tunnel_up", "t1", **_body([DIRECT], relay=GRANT)) is None
    pool.wait_for("session_status", "failed")
    assert time.monotonic() - began < pool.sessions.timing.connect_s / 2
    # The hub's command is answered with the code, not with a report of
    # `none`, which the hub would read as `no_path`.
    (refused,) = _refused(pool)
    assert refused["body"]["code"] == "path_too_narrow"
    assert "full-size" in refused["body"]["message"]
    assert pool.box.of_type("tunnel_report") == []
    failed = pool.box.of_type("session_status")[-1]["body"]
    assert failed["error_code"] == "path_too_narrow"
    assert "full-size" in failed["log_excerpt"] and "1172" in failed["log_excerpt"]
    assert "relay" in failed["log_excerpt"]
    assert len(_why(pool)) == 1
    assert pool.docker.of_session("s1") == []


def test_a_last_candidate_that_loses_full_size_packets_is_too_narrow_as_well(
    pool: Pool,
) -> None:
    # No relay to fall back to: the narrow candidate was the last path.
    pool.docker.narrow = {(fakes.PEER_ADDRESS, 51820)}
    _prepare(pool)
    assert pool.ask("tunnel_up", "t1", **_body([LAN])) is None
    pool.wait_for("session_status", "failed")
    (refused,) = _refused(pool)
    assert refused["body"]["code"] == "path_too_narrow"
    failed = pool.box.of_type("session_status")[-1]["body"]
    assert failed["error_code"] == "path_too_narrow"
    assert "candidate" in failed["log_excerpt"]


def test_a_peer_that_never_answers_still_fails_as_no_path(pool: Pool) -> None:
    pool.docker.answering = set()
    _prepare(pool)
    report = pool.up("t1", **_body([DIRECT], relay=GRANT))
    assert report["body"]["peers"] == [{"rig_id": "rig-peer", "path": "none"}]
    pool.wait_for("session_status", "failed")
    failed = pool.box.of_type("session_status")[-1]["body"]
    assert failed["error_code"] == "no_path"
    assert _refused(pool) == [] and _why(pool) == []


def test_a_relay_that_never_answers_after_a_narrow_candidate_is_no_path(
    pool: Pool,
) -> None:
    # The last path, the relay, never answered: that is what failed. What the
    # candidate before it lost is still said.
    pool.docker.narrow = {(fakes.PEER_ADDRESS, 51820)}
    pool.docker.answering = {(fakes.PEER_ADDRESS, 51820)}
    _prepare(pool)
    report = pool.up("t1", **_body([LAN], relay=GRANT))
    assert report["body"]["peers"] == [{"rig_id": "rig-peer", "path": "none"}]
    pool.wait_for("session_status", "failed")
    failed = pool.box.of_type("session_status")[-1]["body"]
    assert failed["error_code"] == "no_path"
    assert "full-size" in failed["log_excerpt"]
    assert _refused(pool) == []


def test_a_path_that_carries_both_pings_is_taken_as_before(pool: Pool) -> None:
    _prepare(pool)
    report = pool.up("t1", **_body([LAN, DIRECT]))
    (peer,) = report["body"]["peers"]
    assert peer["path"] == "lan" and peer["endpoint"] == LAN
    assert peer["rtt_us"] == 512
    assert _why(pool) == []


def test_a_path_whose_pings_say_nothing_of_full_size_is_taken_as_before() -> None:
    from mcgyvr.rig import pooled

    assert pooled.read_ping("0.512\nfull ok 1172\n") == pooled.PingSeen(
        rtt_ms=0.512, full=True, size=1172
    )
    assert pooled.read_ping("0.512\nfull lost 1172\n") == pooled.PingSeen(
        rtt_ms=0.512, full=False, size=1172
    )
    # No small ping answered: the full-size one says nothing of the path's MTU.
    assert not pooled.read_ping("full lost 1172\n").narrow
    assert pooled.read_ping("0.512\nfull lost 1172\n").narrow
    assert not pooled.read_ping("0.512\nfull ok 1172\n").narrow
    for unread in ("0.512\n", "", "nan\nfull lost 1172\n", "0.5\nfull lost x\n"):
        assert not pooled.read_ping(unread).narrow, unread
    assert pooled.read_ping("0.512\n").rtt_ms == 0.512


def test_the_full_size_ping_is_the_size_of_the_tunnels_own_interface() -> None:
    from mcgyvr.rig import pooled

    lines = pooled.PING_SCRIPT.splitlines()
    measured = next(i for i, line in enumerate(lines) if "min\\/avg" in line)
    sized = next(i for i, line in enumerate(lines) if "/sys/class/net/wg0/mtu" in line)
    full = next(i for i, line in enumerate(lines) if '-s "$size"' in line)
    assert measured < sized < full
    # An IPv4 header (20) and an ICMP header (8) around the ping's data.
    assert pooled.PING_HEADERS == 20 + 8
    assert f"- {pooled.PING_HEADERS} " in lines[sized]
    assert f"-c {pooled.FULL_PINGS} " in lines[full]
