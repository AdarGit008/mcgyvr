"""A session resumes when the hub returns within its grace, and only then.

When the agent's channel drops, the hub keeps the rig's sessions for its
grace (the schema's ``x-reconnect-grace-s``) and so does the rig. While they
wait, the agent hurries back. A hello within the grace names the sessions
still running, and the hub resumes those it knows; on its return each one
says where it stands now (what it said while the channel was down was lost
with it). A session the hub does not know is torn down: the hub stops it, or
answers what it said of it with ``unknown_session``. A hub that stays away
past the grace takes every session down (``test_a_session_is_torn_down…``).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from tests import rig_pool_fakes as fakes
from tests.rig_pool_fakes import Pool, make_pool, prepared


@pytest.fixture
def pool(tmp_path: Path) -> Iterator[Pool]:
    made = make_pool(tmp_path)
    yield made
    made.sessions.close()


def _ready_worker(pool: Pool) -> None:
    prepared(pool)
    pool.up("t1", **fakes.tunnel_up_body())
    cards = [{"card_index": 0, "port": 50052}]
    assert pool.ask("worker_start", "w1", session_id="s1", cards=cards) is not None
    pool.wait_for("session_status", "ready")


def test_the_rig_waits_for_the_hub_only_while_a_session_waits_for_it(
    pool: Pool,
) -> None:
    assert not pool.sessions.waiting()
    pool.sessions.offline()
    assert not pool.sessions.waiting()  # no session: nothing to hurry back for
    pool.sessions.online()
    _ready_worker(pool)
    pool.sessions.offline()
    assert pool.sessions.waiting()
    pool.sessions.online()
    assert not pool.sessions.waiting()


def test_a_resumed_session_says_where_it_stands_on_the_hubs_return(
    pool: Pool,
) -> None:
    _ready_worker(pool)
    pool.sessions.offline()
    before = len(pool.box.of_type("session_status"))
    pool.sessions.online()
    pool.wait_for("session_status", "ready", count=2)
    said = pool.box.of_type("session_status")[before:]
    assert [f["body"] for f in said] == [
        {"session_id": "s1", "state": "ready", "role": "worker"}
    ]
    assert "re" not in said[0]
    assert pool.sessions.running() == ("s1",)


def test_a_session_the_hub_does_not_know_is_torn_down(pool: Pool) -> None:
    from mcgyvr.rig import protocol

    _ready_worker(pool)
    pool.sessions.offline()
    pool.sessions.online()
    pool.wait_for("session_status", "ready", count=2)
    told = pool.box.of_type("session_status")[-1]
    pool.sessions.hub_error(
        protocol.Error(re="not-a-frame-of-ours", code="unknown_session", message="")
    )
    pool.sessions.hub_error(protocol.Error(re=told["id"], code="busy", message=""))
    assert pool.sessions.running() == ("s1",)
    pool.sessions.hub_error(
        protocol.Error(re=told["id"], code="unknown_session", message="")
    )
    pool.wait_for("session_status", "stopped")
    assert pool.docker.of_session("s1") == []


def test_a_session_the_hub_stops_on_its_return_is_torn_down(pool: Pool) -> None:
    _ready_worker(pool)
    pool.sessions.offline()
    pool.sessions.online()
    ack = pool.ask("session_stop", "x1", session_id="s1", reason="unknown")
    assert ack is not None and ack["type"] == "ack"
    pool.wait_for("session_status", "stopped")
    assert pool.docker.of_session("s1") == []


def test_the_rigs_grace_is_the_hubs() -> None:
    from mcgyvr.rig import session
    from tests import rig_schema

    assert session.Timing().grace_s == rig_schema.load()["x-reconnect-grace-s"]
