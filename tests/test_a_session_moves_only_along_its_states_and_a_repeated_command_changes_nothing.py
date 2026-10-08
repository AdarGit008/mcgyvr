"""A session moves only along its states, and a repeated command changes nothing.

The hub prepares a session on a rig, brings its tunnel up, starts a worker or
a head in it, asks where it stands, and stops it. The agent keeps one state
per session — ``preparing``, ``prepared``, ``tunnel_up``, ``starting``,
``loading``, ``ready``, ``failed``, ``stopped`` — and moves only along the
edges its table names; a command that comes too early is answered
``not_ready``, one for the other role ``not_capable``, and nothing is started.

Every command may be retried: the same command again gets the same answer
and starts nothing more (one tunnel, one worker per card, one head), and the
same session asked to do something else is refused. Every frame the agent
sends is valid against the hub's published schema.
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


def test_the_table_lets_every_live_state_end_and_no_ended_state_start_again() -> None:
    from mcgyvr.rig import session as rs
    from mcgyvr.rig import sessionwire

    assert set(rs.TRANSITIONS) == set(sessionwire.STATES) - {"absent"}
    for state, onward in rs.TRANSITIONS.items():
        if state in ("failed", "stopped"):
            assert onward <= {"stopped"}
        else:
            assert {"failed", "stopped"} <= onward
    assert "ready" not in rs.TRANSITIONS["prepared"]
    assert rs.TRANSITIONS["stopped"] == frozenset()


def test_a_worker_session_runs_prepare_tunnel_start_query_stop(pool: Pool) -> None:
    from mcgyvr.rig import pooled

    answer = prepared(pool)
    assert answer["re"] == "p1"
    assert answer["body"] == {
        "session_id": "s1",
        "public_key": fakes.KEY,
        "listen_port": 51820,
        "endpoints": [{"host": fakes.LAN_ADDRESS, "port": 51820, "kind": "lan"}],
    }
    assert pool.docker.runs() == [pooled.container_name("s1", "tunnel")]

    report = pool.up("t1", **fakes.tunnel_up_body())
    assert report["re"] == "t1"
    assert report["body"]["peers"][0]["path"] == "lan"
    pool.settle()
    tunnel_calls = [s for s in pool.docker.scripts if s[1] == pooled.TUNNEL_SCRIPT]
    assert [call[2] for call in tunnel_calls] == [
        (
            f"{fakes.SELF}/24",
            "51820",
            fakes.PEER_KEY,
            fakes.PEER_ADDRESS,
            "51820",
            "25",
            f"{fakes.PEER}/32",
        )
    ]
    status = pool.ask("session_query", "q1", session_id="s1")
    assert status is not None and status["body"]["state"] == "tunnel_up"

    ack = pool.ask(
        "worker_start", "w1", session_id="s1", cards=[{"card_index": 1, "port": 50052}]
    )
    assert ack is not None and ack["type"] == "ack"
    pool.wait_for("session_status", "ready")
    assert pooled.container_name("s1", "worker-1") in pool.docker.runs()
    opened = [s for s in pool.docker.scripts if s[1] == pooled.OPEN_WORKER_SCRIPT]
    assert [call[2] for call in opened] == [(fakes.SELF, "50052", f"{fakes.PEER}/32")]

    status = pool.ask("session_query", "q2", session_id="s1")
    assert status is not None
    assert status["re"] == "q2" and status["type"] == "session_status"
    assert status["body"] == {"session_id": "s1", "state": "ready", "role": "worker"}

    ack = pool.ask("session_stop", "x1", session_id="s1", reason="done")
    assert ack is not None and ack["type"] == "ack"
    pool.wait_for("session_status", "stopped")
    assert pool.docker.of_session("s1") == []
    status = pool.ask("session_query", "q3", session_id="s1")
    assert status is not None and status["body"]["state"] == "stopped"


def test_every_command_repeated_gets_the_same_answer_and_starts_nothing_more(
    pool: Pool,
) -> None:
    first = prepared(pool)
    again = pool.ask("session_prepare", "p2", session_id="s1", role="worker")
    assert again is not None and again["type"] == "session_prepared"
    assert again["body"] == first["body"] and again["re"] == "p2"

    body = fakes.tunnel_up_body()
    reports = [pool.up("t1", **body)]
    for attempt in ("t2", "t3"):
        again = pool.ask("tunnel_up", attempt, **body)
        assert again is not None and again["type"] == "tunnel_report"
        reports.append(again)
    assert all(r["body"] == reports[0]["body"] for r in reports)
    cards = [{"card_index": 0, "port": 50052}, {"card_index": 1, "port": 50053}]
    for attempt in ("w1", "w2"):
        ack = pool.ask("worker_start", attempt, session_id="s1", cards=cards)
        assert ack is not None and ack["type"] == "ack"
    pool.wait_for("session_status", "ready")
    pool.settle()
    from mcgyvr.rig import pooled

    tunnels = [s for s in pool.docker.scripts if s[1] == pooled.TUNNEL_SCRIPT]
    assert len(tunnels) == 1
    assert sorted(pool.docker.runs()) == sorted(
        pooled.container_name("s1", part) for part in ("tunnel", "worker-0", "worker-1")
    )
    for attempt in ("x1", "x2"):
        ack = pool.ask("session_stop", attempt, session_id="s1")
        assert ack is not None and ack["type"] == "ack"
    pool.wait_for("session_status", "stopped")
    pool.settle()
    assert len(pool.box.of_type("session_status")) == 2  # ready, stopped: once each


def test_the_same_session_asked_for_something_else_is_refused(pool: Pool) -> None:
    prepared(pool)
    other_role = pool.ask("session_prepare", "p2", session_id="s1", role="head")
    assert other_role is not None and other_role["body"]["code"] == "bad_message"
    pool.up("t1", **fakes.tunnel_up_body())
    moved = fakes.tunnel_up_body(address=f"{fakes.PEER.rsplit('.', 1)[0]}.9/24")
    refused = pool.ask("tunnel_up", "t2", **moved)
    assert refused is not None and refused["body"]["code"] == "bad_message"
    cards = [{"card_index": 0, "port": 50052}]
    assert pool.ask("worker_start", "w1", session_id="s1", cards=cards)["type"] == "ack"  # type: ignore[index]
    other = pool.ask(
        "worker_start", "w2", session_id="s1", cards=[{"card_index": 1, "port": 50052}]
    )
    assert other is not None and other["body"]["code"] == "bad_message"


def test_a_command_that_comes_too_early_or_for_the_other_role_starts_nothing(
    pool: Pool,
) -> None:
    pool.docker.tunnel_ready = False
    assert pool.ask("session_prepare", "p1", session_id="s1", role="worker") is None
    early = pool.ask("tunnel_up", "t1", **fakes.tunnel_up_body())
    assert early is not None and early["body"]["code"] == "not_ready"
    pool.docker.tunnel_ready = True
    pool.wait_for("session_prepared")
    cards = [{"card_index": 0, "port": 50052}]
    before = pool.ask("worker_start", "w1", session_id="s1", cards=cards)
    assert before is not None and before["body"]["code"] == "not_ready"
    head = pool.ask(
        "head_start",
        "h1",
        session_id="s1",
        model={"name": fakes.MODEL},
        ctx=4096,
        devices=[{"kind": "local", "card_index": 0}],
        tensor_split=[1],
    )
    assert head is not None and head["body"]["code"] == "not_capable"
    pool.settle()
    assert len(pool.docker.runs()) == 1  # the tunnel, and nothing after it


def test_a_head_session_loads_then_is_ready_on_its_cards_and_its_workers(
    pool: Pool,
) -> None:
    from mcgyvr.rig import pooled

    prepared(pool, role="head")
    tunnel_argv = pool.docker.containers[pooled.container_name("s1", "tunnel")].argv
    assert "127.0.0.1:18080:8080/tcp" in tunnel_argv
    body = fakes.tunnel_up_body(address=f"{fakes.PEER}/24")
    body["peers"][0]["allowed_ips"] = [f"{fakes.SELF}/32"]
    pool.up("t1", **body)
    ack = pool.ask(
        "head_start",
        "h1",
        session_id="s1",
        model={"name": fakes.MODEL},
        ctx=12288,
        devices=[
            {"kind": "local", "card_index": 1},
            {"kind": "local", "card_index": 0},
            {"kind": "rpc", "host": fakes.SELF, "port": 50052},
        ],
        tensor_split=[10, 10, 5],
    )
    assert ack is not None and ack["type"] == "ack"
    pool.wait_for("session_status", "loading")
    pool.wait_for("session_status", "ready")
    head = pool.docker.containers[pooled.container_name("s1", "head")].argv
    assert head[head.index("--gpus") + 1] == '"device=0,1"'
    assert head[head.index("-dev") + 1] == "CUDA1,CUDA0,RPC0"
    assert head[head.index("-ts") + 1] == "10,10,5"
    assert head[head.index("--rpc") + 1] == f"{fakes.SELF}:50052"
    assert head[head.index("-m") + 1] == f"/models/dense/{fakes.MODEL}"
    assert head[head.index("--host") + 1] == fakes.BRIDGE.split("/")[0]
    assert f"{tmp_models(pool)}:/models:ro" in head
    opened = [s for s in pool.docker.scripts if s[1] == pooled.OPEN_HEAD_SCRIPT]
    assert [call[2] for call in opened] == [
        (fakes.PEER, fakes.GATEWAY, fakes.SELF, "50052")
    ]
    assert pool.sessions.head_port("s1") == 18080
    rtt = pool.box.of_type("peer_rtt")
    assert rtt and rtt[0]["body"]["samples"] == [{"rig_id": "rig-peer", "rtt_us": 512}]


def tmp_models(pool: Pool) -> str:
    inventory = pool.sessions.machine.inventory()
    return str(inventory.folder)


def test_a_session_nobody_prepared_is_absent_and_stopping_it_is_no_error(
    pool: Pool,
) -> None:
    status = pool.ask("session_query", "q1", session_id="nobody")
    assert status is not None
    assert status["body"] == {"session_id": "nobody", "state": "absent"}
    ack = pool.ask("session_stop", "x1", session_id="nobody")
    assert ack is not None and ack["type"] == "ack" and ack["re"] == "x1"
    assert pool.docker.calls == []


def test_the_hello_names_the_sessions_running_and_only_those(pool: Pool) -> None:
    assert pool.sessions.running() == ()
    prepared(pool)
    assert pool.sessions.running() == ("s1",)
    pool.ask("session_stop", "x1", session_id="s1")
    pool.wait_for("session_status", "stopped")
    assert pool.sessions.running() == ()
