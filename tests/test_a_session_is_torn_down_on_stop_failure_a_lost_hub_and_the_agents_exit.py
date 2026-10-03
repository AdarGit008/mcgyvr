"""A session is torn down on stop, on failure, on a lost hub, and on the agent's exit.

An RPC server runs any compute graph its head sends, so one left running with
nobody owning it is the failure this file exists for. Whatever ends a
session — the hub stops it, a container fails to start or exits later, the
tunnel will not come up, the hub stays away past the grace a reconnect gets,
or the agent itself ends — every container of the session is removed (the
key dies with the tunnel's), the hub is told ``failed`` with the code and a
bounded excerpt of what the engine said, and nothing of it is left on the
daemon. While a session lives its tunnel's lease is renewed; an agent that
dies without a word lets it run out (the tunnel then takes its engine down),
and the next agent removes what a dead one left, and nothing a live one owns.
"""

from __future__ import annotations

import os
import time
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


def _worker(pool: Pool, cards: list[int] | None = None) -> None:
    prepared(pool)
    assert pool.ask("tunnel_up", "t1", **fakes.tunnel_up_body())["type"] == "ack"  # type: ignore[index]
    body = [{"card_index": c, "port": 50052 + c} for c in (cards or [0])]
    assert pool.ask("worker_start", "w1", session_id="s1", cards=body)["type"] == "ack"  # type: ignore[index]


def test_a_worker_that_exits_on_start_fails_the_session_and_leaves_nothing(
    pool: Pool,
) -> None:
    pool.docker.exits_on_start.add("worker-0")
    _worker(pool)
    pool.wait_for("session_status", "failed")
    failed = pool.box.of_type("session_status")[-1]["body"]
    assert failed["error_code"] == "start_failed" and failed["role"] == "worker"
    assert "engine said: load failed" in failed["log_excerpt"]
    assert pool.docker.of_session("s1") == []
    status = pool.ask("session_query", "q1", session_id="s1")
    assert status is not None and status["body"]["state"] == "failed"
    assert status["body"]["error_code"] == "start_failed"


def test_a_worker_that_never_listens_fails_on_time_and_leaves_nothing(
    pool: Pool,
) -> None:
    pool.docker.listening = False
    _worker(pool)
    pool.wait_for("session_status", "failed")
    assert pool.box.of_type("session_status")[-1]["body"]["error_code"] == (
        "start_failed"
    )
    assert pool.docker.of_session("s1") == []


def test_a_worker_that_exits_after_it_was_ready_fails_the_session(pool: Pool) -> None:
    _worker(pool)
    pool.wait_for("session_status", "ready")
    from mcgyvr.sandbox import pooled

    name = pooled.container_name("s1", "worker-0")
    with pool.docker.lock:
        pool.docker.containers[name].state = "exited"
    pool.wait_for("session_status", "failed")
    assert pool.docker.of_session("s1") == []


def test_a_tunnel_that_never_says_ready_fails_the_prepare_and_is_removed(
    pool: Pool,
) -> None:
    pool.docker.tunnel_ready = False
    assert pool.ask("session_prepare", "p1", session_id="s1", role="worker") is None
    pool.wait_for("session_status", "failed")
    assert pool.box.of_type("session_status")[-1]["body"]["error_code"] == (
        "tunnel_failed"
    )
    assert pool.docker.of_session("s1") == []
    assert not pool.box.of_type("session_prepared")


def test_a_tunnel_that_cannot_be_configured_fails_and_is_removed(pool: Pool) -> None:
    pool.docker.fail_script = "TUNNEL_SCRIPT"
    prepared(pool)
    assert pool.ask("tunnel_up", "t1", **fakes.tunnel_up_body())["type"] == "ack"  # type: ignore[index]
    pool.wait_for("session_status", "failed")
    body = pool.box.of_type("session_status")[-1]["body"]
    assert body["error_code"] == "tunnel_failed"
    assert pool.docker.of_session("s1") == []


def test_a_hub_that_stays_away_past_the_grace_takes_the_session_down(
    pool: Pool,
) -> None:
    _worker(pool)
    pool.wait_for("session_status", "ready")
    pool.sessions.offline()
    deadline = time.monotonic() + 5
    while pool.docker.of_session("s1") and time.monotonic() < deadline:
        time.sleep(0.01)
    assert pool.docker.of_session("s1") == []
    assert pool.sessions.running() == ()


def test_a_hub_that_returns_within_the_grace_keeps_the_session(pool: Pool) -> None:
    _worker(pool)
    pool.wait_for("session_status", "ready")
    pool.sessions.offline()
    pool.sessions.online()
    time.sleep(pool.sessions.timing.grace_s * 3)
    assert pool.sessions.running() == ("s1",)
    assert pool.docker.of_session("s1")


def test_the_agents_exit_takes_every_session_down(pool: Pool) -> None:
    _worker(pool, cards=[0, 1])
    pool.wait_for("session_status", "ready")
    assert len(pool.docker.of_session("s1")) == 3
    pool.sessions.close()
    assert pool.docker.of_session("s1") == []
    assert pool.docker.containers == {}
    refused = pool.ask("session_prepare", "p9", session_id="s2", role="worker")
    assert refused is not None and refused["body"]["code"] == "not_capable"


def test_a_living_sessions_lease_is_renewed(pool: Pool) -> None:
    _worker(pool)
    pool.wait_for("session_status", "ready")
    before = pool.docker.leases
    time.sleep(pool.sessions.timing.renew_s * 5)
    assert pool.docker.leases > before


def test_the_next_agent_removes_what_a_dead_one_left_and_nothing_a_live_one_owns(
    tmp_path: Path,
) -> None:
    made = make_pool(tmp_path)
    try:
        dead_pid = _a_pid_that_is_not_running()
        made.docker.start(_argv("left-tunnel", "old", dead_pid))
        made.docker.start(_argv("left-worker", "old", dead_pid))
        made.docker.start(_argv("other-tunnel", "theirs", os.getppid()))
        removed = made.sessions.sweep()
        assert sorted(removed) == ["left-tunnel", "left-worker"]
        assert sorted(made.docker.containers) == ["other-tunnel"]
    finally:
        made.sessions.close()


def _argv(name: str, session: str, pid: int) -> list[str]:
    return [
        "run",
        "--name",
        name,
        "--label",
        "mcgyvr.pool=1",
        "--label",
        f"mcgyvr.pool.session={session}",
        "--label",
        f"mcgyvr.pool.agent={pid}",
        "image",
    ]


def _a_pid_that_is_not_running() -> int:
    pid = 2**22 - 1
    while pid > 1:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return pid
        except PermissionError:
            pass
        pid -= 1
    raise AssertionError("every pid is running")


def test_the_tunnel_ends_itself_when_its_lease_runs_out_and_takes_its_engine() -> None:
    from mcgyvr.sandbox import pooled

    entry = pooled.TUNNEL_ENTRY
    assert 'if [ $((now - seen)) -gt "$lease_s" ]' in entry
    assert 'kill "$wg_pid"' in entry
    guard = pooled.GUARD_SCRIPT
    assert "/sys/class/net/wg0" in guard and "exit 70" in guard
