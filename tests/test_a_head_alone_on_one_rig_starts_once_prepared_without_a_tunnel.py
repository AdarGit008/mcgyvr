"""A head alone on one rig starts once prepared, without a tunnel.

When the model fits one rig, the hub's session has no workers: it prepares
the head (``session_prepare``), brings no tunnel up, and starts the head on
this rig's own cards (``head_start`` with local devices only). Preparing is
still what makes the session this rig's — its head runs in the session's
tunnel container, which owns its network and publishes its API on loopback —
but with no peers there is nothing for ``tunnel_up`` to do, so the head does
not wait for it. A head that names an RPC device still does: those are
reached only over the tunnel. A head for a session never prepared is unknown.
Every frame is checked against the hub's published schema.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes
from tests.rig_pool_fakes import Pool, make_pool, prepared


@pytest.fixture
def pool(tmp_path: Path) -> Iterator[Pool]:
    made = make_pool(tmp_path)
    yield made
    made.sessions.close()


def head_start(pool: Pool, message_id: str, *devices: dict[str, Any]) -> Any:
    return pool.ask(
        "head_start",
        message_id,
        session_id="s1",
        model={"name": fakes.MODEL},
        ctx=4096,
        devices=list(devices),
        tensor_split=[1] * len(devices),
    )


LOCAL_0 = {"kind": "local", "card_index": 0}
LOCAL_1 = {"kind": "local", "card_index": 1}


def test_a_prepared_head_with_only_its_own_cards_loads_and_is_ready(
    pool: Pool,
) -> None:
    from mcgyvr.rig import pooled

    prepared(pool, role="head")
    ack = head_start(pool, "h1", LOCAL_1, LOCAL_0)
    assert ack is not None and ack["type"] == "ack" and ack["re"] == "h1"
    pool.wait_for("session_status", "loading")
    pool.wait_for("session_status", "ready")

    head = pool.docker.containers[pooled.container_name("s1", "head")].argv
    assert head[head.index("--gpus") + 1] == '"device=0,1"'
    assert head[head.index("-dev") + 1] == "CUDA1,CUDA0"
    assert "--rpc" not in head
    assert head[head.index("--host") + 1] == fakes.BRIDGE.split("/")[0]
    # no tunnel was configured, and the API is let through to the agent only
    assert not [s for s in pool.docker.scripts if s[1] == pooled.TUNNEL_SCRIPT]
    opened = [s for s in pool.docker.scripts if s[1] == pooled.OPEN_HEAD_SCRIPT]
    assert [call[2] for call in opened] == [(fakes.BRIDGE.split("/")[0], fakes.GATEWAY)]
    assert pool.sessions.head_port("s1") == 18080
    status = pool.ask("session_query", "q1", session_id="s1")
    assert status is not None
    assert status["body"] == {"session_id": "s1", "state": "ready", "role": "head"}
    assert pool.box.of_type("peer_rtt") == []

    again = head_start(pool, "h2", LOCAL_1, LOCAL_0)
    assert again is not None and again["type"] == "ack"
    pool.settle()
    assert pool.docker.runs().count(pooled.container_name("s1", "head")) == 1


def test_a_head_that_names_a_worker_still_waits_for_the_tunnel(pool: Pool) -> None:
    prepared(pool, role="head")
    early = head_start(
        pool, "h1", LOCAL_0, {"kind": "rpc", "host": fakes.SELF, "port": 50052}
    )
    assert early is not None and early["body"]["code"] == "not_ready"
    pool.settle()
    assert len(pool.docker.runs()) == 1  # the tunnel, and nothing after it


def test_a_head_for_a_session_never_prepared_is_unknown(pool: Pool) -> None:
    refused = head_start(pool, "h1", LOCAL_0)
    assert refused is not None and refused["body"]["code"] == "unknown_session"
    assert pool.docker.calls == []


def test_a_head_asked_before_its_tunnel_container_is_ready_is_not_ready(
    pool: Pool,
) -> None:
    pool.docker.tunnel_ready = False
    assert pool.ask("session_prepare", "p1", session_id="s1", role="head") is None
    early = head_start(pool, "h1", LOCAL_0)
    assert early is not None and early["body"]["code"] == "not_ready"
    pool.docker.tunnel_ready = True
    pool.wait_for("session_prepared")
    ack = head_start(pool, "h2", LOCAL_0)
    assert ack is not None and ack["type"] == "ack"
    pool.wait_for("session_status", "ready")
