"""A rig with no LAN address is prepared, and serves a head on its own cards.

A session of one rig needs no tunnel: its head runs in the session's tunnel
container on this rig's cards, and the hub sends no ``tunnel_up``. The
endpoints a ``session_prepared`` carries are only for peers to reach the
tunnel at, so a rig with none — no LAN address, and none the owner named —
is prepared all the same, with an empty list (the hub's schema allows it),
rather than refused at ``session_prepare``: the agent cannot tell there a
session of one rig from one of several. A session of several rigs that has
nothing to aim at fails where it needs the tunnel, at ``tunnel_up``.
"""

from __future__ import annotations

import dataclasses
import ipaddress
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests import rig_pool_fakes as fakes
from tests.rig_pool_fakes import Pool, make_pool, prepared


def _loopback_only() -> tuple[tuple[str, ipaddress.IPv4Interface], ...]:
    return (("lo", ipaddress.IPv4Interface("127.0.0.1/8")),)


@pytest.fixture
def pool(tmp_path: Path) -> Iterator[Pool]:
    made = make_pool(tmp_path, endpoints=())
    made.sessions.machine = dataclasses.replace(
        made.sessions.machine, interfaces=_loopback_only
    )
    yield made
    made.sessions.close()


@pytest.mark.parametrize("role", ["head", "worker"])
def test_a_rig_with_no_lan_address_is_prepared_with_no_endpoints(
    pool: Pool, role: str
) -> None:
    found = prepared(pool, role=role)
    assert found["body"]["endpoints"] == []
    assert pool.sessions.state_of("s1") == ("prepared", role)


def test_its_head_alone_starts_and_is_ready(pool: Pool) -> None:
    prepared(pool, role="head")
    ack = pool.ask(
        "head_start",
        "h1",
        session_id="s1",
        model={"name": fakes.MODEL},
        ctx=4096,
        devices=[{"kind": "local", "card_index": 0}],
        tensor_split=[1],
    )
    assert ack is not None and ack["type"] == "ack"
    pool.wait_for("session_status", "ready")
    assert pool.sessions.state_of("s1") == ("ready", "head")
