"""A tunnel port rests before another session takes it.

A session's tunnel container publishes its WireGuard UDP port on the host,
and the host forwards the port to the container by address. The host keeps
a UDP flow it forwarded for a while after the flow's last packet (120 s on
Linux for a flow that carried traffic), with the address it forwarded to.
A new session on the same port, with a peer on the same port, is the same
flow to the host: its first packets go where the old session's went, which
may now be another session's container, and the handshake is lost.

So a port a session held is not given to another for
:attr:`mcgyvr.rig.session.Timing.port_rest_s` after that session's teardown:
a new session takes the lowest port of the owner's range that no session
holds and that has rested. The range is small, and a rig whose sessions
start and stop quickly can have every free port still resting: a new
session then takes the free port that has rested longest, and the agent
says so, rather than being refused — a refused start is worse than a first
handshake that may be lost. With every port held a new session is refused
``busy``, as before.
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.rig_pool_fakes import Pool, make_pool


@pytest.fixture
def pool(tmp_path: Path) -> Iterator[Pool]:
    made = make_pool(tmp_path)
    yield made
    made.sessions.close()


def _rest(pool: Pool, seconds: float) -> None:
    pool.sessions.timing = dataclasses.replace(
        pool.sessions.timing, port_rest_s=seconds
    )


def _prepare(pool: Pool, session_id: str) -> int:
    message_id = f"p-{session_id}"
    answer = pool.ask(
        "session_prepare", message_id, session_id=session_id, role="worker"
    )
    assert answer is None, answer
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        for frame in pool.box.of_type("session_prepared"):
            if frame.get("re") == message_id:
                port: int = frame["body"]["listen_port"]
                return port
        time.sleep(0.005)
    raise AssertionError(f"no session_prepared re {message_id} in {pool.box.frames}")


def _stop(pool: Pool, session_id: str, stopped: int) -> None:
    pool.ask("session_stop", f"x-{session_id}", session_id=session_id)
    pool.wait_for("session_status", "stopped", count=stopped)
    pool.settle()


def _busy(answer: Any) -> None:
    assert answer is not None and answer["type"] == "error", answer
    assert answer["body"]["code"] == "busy", answer


def test_a_port_rests_two_minutes_after_its_session() -> None:
    from mcgyvr.rig import session

    # as long as Linux keeps a UDP flow that carried traffic
    assert session.Timing().port_rest_s == 120.0


def test_a_port_just_left_is_not_the_next_sessions(pool: Pool) -> None:
    _rest(pool, 120.0)
    assert _prepare(pool, "s1") == 51820
    _stop(pool, "s1", 1)
    assert _prepare(pool, "s2") == 51821
    assert pool.logged == []


def test_a_unit_started_again_and_again_walks_the_range(pool: Pool) -> None:
    """One unit kept, another restarted: each restart is on a fresh port."""
    _rest(pool, 120.0)
    assert _prepare(pool, "kept") == 51820
    assert _prepare(pool, "a") == 51821
    _stop(pool, "a", 1)
    assert _prepare(pool, "b") == 51822
    _stop(pool, "b", 2)
    assert _prepare(pool, "c") == 51823


def test_a_port_that_has_rested_is_taken_again(pool: Pool) -> None:
    _rest(pool, 1.0)
    assert _prepare(pool, "s1") == 51820
    _stop(pool, "s1", 1)
    assert _prepare(pool, "s2") == 51821
    time.sleep(1.1)
    assert _prepare(pool, "s3") == 51820


def test_with_every_free_port_resting_the_one_that_rested_longest_is_taken(
    pool: Pool,
) -> None:
    from mcgyvr.rig import session

    _rest(pool, 120.0)
    ports = []
    for n in range(session.MAX_LIVE_SESSIONS):
        ports.append(_prepare(pool, f"s{n}"))
        _stop(pool, f"s{n}", n + 1)
    assert ports == [51820, 51821, 51822, 51823]
    assert pool.logged == []
    # nothing has rested: the start is not refused, and takes the port left
    # first, then the one left after it
    assert _prepare(pool, "again") == 51820
    (line,) = pool.logged
    assert "tunnel port 51820" in line and "120 s" in line
    assert _prepare(pool, "more") == 51821


def test_a_resting_port_is_never_one_a_session_holds(pool: Pool) -> None:
    from mcgyvr.rig import session

    _rest(pool, 120.0)
    for n in range(session.MAX_LIVE_SESSIONS):
        _prepare(pool, f"s{n}")
    _busy(pool.ask("session_prepare", "px", session_id="sx", role="worker"))
    _stop(pool, "s2", 1)
    # the only free port is the one just left: taken, the others are held
    assert _prepare(pool, "sy") == 51822
