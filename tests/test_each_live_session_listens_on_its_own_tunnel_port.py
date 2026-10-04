"""Each live session has a tunnel port of its own, and a head API port of its own.

A session's tunnel container publishes its WireGuard UDP port on the host,
so two sessions at once cannot share one. The owner's ``listen_port`` is the
first of a small range: a session takes the lowest port of
``listen_port`` .. ``listen_port + MAX_LIVE_SESSIONS - 1`` that no session
holds, so a rig in one session listens where it always did. The port
travels in the session's own ``session_prepared`` (``listen_port`` and each
endpoint's ``port``), the hub hands it back in ``tunnel_up``, and the
tunnel is published and started on it. A port is held until the session
holding it is torn down. With every port of the range held — or none left
below 65536 — a new session is refused ``busy``.

A head's API is published on a loopback port of its own too; a port the
machine offers that another session holds is not taken.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes
from tests.rig_pool_fakes import Pool, make_pool


@pytest.fixture
def pool(tmp_path: Path) -> Iterator[Pool]:
    made = make_pool(tmp_path)
    yield made
    made.sessions.close()


def _prepare(pool: Pool, session_id: str, role: str, message_id: str) -> Any:
    answer = pool.ask("session_prepare", message_id, session_id=session_id, role=role)
    assert answer is None, answer
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        for frame in pool.box.of_type("session_prepared"):
            if frame.get("re") == message_id:
                return frame
        time.sleep(0.005)
    raise AssertionError(f"no session_prepared re {message_id} in {pool.box.frames}")


def _tunnel_argv(pool: Pool, session_id: str) -> list[str]:
    from mcgyvr.sandbox import pooled

    return pool.docker.containers[pooled.container_name(session_id, "tunnel")].argv


def _published(argv: list[str]) -> list[str]:
    return [argv[i + 1] for i, word in enumerate(argv[:-1]) if word == "--publish"]


def _busy(answer: Any) -> None:
    assert answer is not None and answer["type"] == "error", answer
    assert answer["body"]["code"] == "busy", answer


def test_one_session_listens_on_the_owners_port(pool: Pool) -> None:
    prepared = _prepare(pool, "s1", "worker", "p1")
    assert prepared["body"]["listen_port"] == 51820
    assert _published(_tunnel_argv(pool, "s1")) == [
        f"{fakes.LAN_ADDRESS}:51820:51820/udp"
    ]


def test_a_second_live_session_listens_on_the_next_port(pool: Pool) -> None:
    first = _prepare(pool, "s1", "worker", "p1")
    second = _prepare(pool, "s2", "worker", "p2")
    assert first["body"]["listen_port"] == 51820
    assert second["body"]["listen_port"] == 51821
    assert second["body"]["endpoints"] == [
        {"host": fakes.LAN_ADDRESS, "port": 51821, "kind": "lan"}
    ]
    argv = _tunnel_argv(pool, "s2")
    assert _published(argv) == [f"{fakes.LAN_ADDRESS}:51821:51821/udp"]
    assert argv[-2:] == ["51821", "60"]  # the tunnel's entry: port, then lease


def test_the_tunnel_comes_up_on_its_own_sessions_port(pool: Pool) -> None:
    from mcgyvr.sandbox import pooled

    _prepare(pool, "s1", "worker", "p1")
    _prepare(pool, "s2", "worker", "p2")
    wrong = pool.ask(
        "tunnel_up", "t0", **fakes.tunnel_up_body(session_id="s2", listen_port=51820)
    )
    assert wrong is not None and wrong["body"]["code"] == "bad_message", wrong
    pool.up("t2", **fakes.tunnel_up_body(session_id="s2", listen_port=51821))
    pool.settle()
    up = [
        s
        for s in pool.docker.scripts
        if s[1] == pooled.TUNNEL_SCRIPT
        and s[0] == pooled.container_name("s2", "tunnel")
    ]
    assert [call[2][1] for call in up] == ["51821"]
    aimed = [
        s
        for s in pool.docker.scripts
        if s[1] == pooled.PATH_SCRIPT and s[0] == pooled.container_name("s2", "tunnel")
    ]
    assert aimed and all(call[2][0] == "51821" for call in aimed)


def test_a_port_is_free_again_once_its_session_is_torn_down(pool: Pool) -> None:
    _prepare(pool, "s1", "worker", "p1")
    _prepare(pool, "s2", "worker", "p2")
    pool.ask("session_stop", "x1", session_id="s1")
    pool.wait_for("session_status", "stopped")
    pool.settle()
    third = _prepare(pool, "s3", "worker", "p3")
    assert third["body"]["listen_port"] == 51820


def test_the_range_starts_at_the_owners_port(tmp_path: Path) -> None:
    made = make_pool(tmp_path, listen_port=40000)
    try:
        ports = [
            _prepare(made, f"s{n}", "worker", f"p{n}")["body"]["listen_port"]
            for n in (1, 2)
        ]
        assert ports == [40000, 40001]
    finally:
        made.sessions.close()


def test_with_every_port_of_the_range_held_a_new_session_is_busy(pool: Pool) -> None:
    from mcgyvr.rig import protocol, session

    # the hello names at most this many sessions, and the hub resumes only
    # those it names
    assert session.MAX_LIVE_SESSIONS == protocol.MAX_SESSIONS_REPORTED
    ports = [
        _prepare(pool, f"s{n}", "worker", f"p{n}")["body"]["listen_port"]
        for n in range(session.MAX_LIVE_SESSIONS)
    ]
    assert ports == [51820 + n for n in range(session.MAX_LIVE_SESSIONS)]
    runs = len(pool.docker.runs())
    _busy(pool.ask("session_prepare", "px", session_id="sx", role="worker"))
    pool.settle()
    assert len(pool.docker.runs()) == runs


def test_no_port_past_the_last_is_taken(tmp_path: Path) -> None:
    made = make_pool(tmp_path, listen_port=65535)
    try:
        assert _prepare(made, "s1", "worker", "p1")["body"]["listen_port"] == 65535
        _busy(made.ask("session_prepare", "p2", session_id="s2", role="worker"))
    finally:
        made.sessions.close()


def test_two_heads_publish_their_apis_on_ports_of_their_own(pool: Pool) -> None:
    _prepare(pool, "h1", "head", "p1")
    _prepare(pool, "h2", "head", "p2")
    apis = [
        [p for p in _published(_tunnel_argv(pool, sid)) if p.startswith("127.0.0.1:")]
        for sid in ("h1", "h2")
    ]
    assert len(apis[0]) == 1 and len(apis[1]) == 1
    assert apis[0] != apis[1]


def test_a_loopback_port_another_session_holds_is_not_taken(tmp_path: Path) -> None:
    from dataclasses import replace

    made = make_pool(tmp_path)
    offered = iter([18080, 18080, 18080, 18090])
    made.sessions.machine = replace(
        made.sessions.machine, free_port=lambda: next(offered)
    )
    try:
        _prepare(made, "h1", "head", "p1")
        _prepare(made, "h2", "head", "p2")
        assert "127.0.0.1:18080:8080/tcp" in _published(_tunnel_argv(made, "h1"))
        assert "127.0.0.1:18090:8080/tcp" in _published(_tunnel_argv(made, "h2"))
    finally:
        made.sessions.close()
