"""A rig runs several sessions at once, one unit per card, and never two on one card.

The hub may place two units on different cards of one rig: a small model's
head on card 0 while card 1 is a worker of a larger model spanning another
rig. Each is a session of its own, with its own tunnel container, so the
agent takes a second ``session_prepare`` while another session lives, and
refuses ``busy`` only for what would share a card:

* ``worker_start`` or ``head_start`` naming a card another live session
  already holds is refused ``busy``, and starts nothing;
* ``session_prepare`` names no card, so it is refused ``busy`` only when no
  lent card is left: every one is held by a live session.

A session holds its cards from the command that named them until it is torn
down. Stopping one session removes its containers alone; the other keeps
running, its lease renewed, and the stopped one's cards are free again. The
agent says it does this with the ``multi_session`` feature, so the hub
places units per card only on a rig whose agent lists it.
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
    """``session_prepare``; the ``session_prepared`` answering it."""
    answer = pool.ask("session_prepare", message_id, session_id=session_id, role=role)
    assert answer is None, answer
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        for frame in pool.box.of_type("session_prepared"):
            if frame.get("re") == message_id:
                return frame
        time.sleep(0.005)
    raise AssertionError(f"no session_prepared re {message_id} in {pool.box.frames}")


def _state(pool: Pool, session_id: str, state: str) -> None:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if pool.sessions.state_of(session_id)[0] == state:
            return
        time.sleep(0.005)
    raise AssertionError(f"{session_id} is {pool.sessions.state_of(session_id)}")


def _head_on(pool: Pool, session_id: str, message_id: str, *cards: int) -> Any:
    return pool.ask(
        "head_start",
        message_id,
        session_id=session_id,
        model={"name": fakes.MODEL},
        ctx=4096,
        devices=[{"kind": "local", "card_index": card} for card in cards],
        tensor_split=[1] * len(cards),
    )


def _worker_on(pool: Pool, session_id: str, message_id: str, *cards: int) -> Any:
    return pool.ask(
        "worker_start",
        message_id,
        session_id=session_id,
        cards=[{"card_index": card, "port": 50052 + card} for card in cards],
    )


def _up(pool: Pool, session_id: str, port: int, message_id: str) -> None:
    pool.up(message_id, **fakes.tunnel_up_body(session_id=session_id, listen_port=port))


def _busy(answer: Any) -> None:
    assert answer is not None and answer["type"] == "error", answer
    assert answer["body"]["code"] == "busy", answer


def _head_and_worker(pool: Pool) -> None:
    """``h1``: a head alone on card 0; ``w2``: a worker on card 1."""
    _prepare(pool, "h1", "head", "p1")
    ack = _head_on(pool, "h1", "c1", 0)
    assert ack is not None and ack["type"] == "ack", ack
    _state(pool, "h1", "ready")
    prepared = _prepare(pool, "w2", "worker", "p2")
    _up(pool, "w2", prepared["body"]["listen_port"], "t2")
    ack = _worker_on(pool, "w2", "c2", 1)
    assert ack is not None and ack["type"] == "ack", ack
    _state(pool, "w2", "ready")


def test_a_second_session_is_prepared_while_another_lives(pool: Pool) -> None:
    from mcgyvr.sandbox import pooled

    _prepare(pool, "s1", "worker", "p1")
    second = _prepare(pool, "s2", "head", "p2")
    assert second["body"]["session_id"] == "s2"
    assert pool.docker.runs() == [
        pooled.container_name("s1", "tunnel"),
        pooled.container_name("s2", "tunnel"),
    ]
    assert set(pool.sessions.running()) == {"s1", "s2"}


def test_two_sessions_on_different_cards_run_at_once(pool: Pool) -> None:
    from mcgyvr.sandbox import pooled

    _head_and_worker(pool)
    assert pool.sessions.state_of("h1") == ("ready", "head")
    assert pool.sessions.state_of("w2") == ("ready", "worker")
    head = pool.docker.containers[pooled.container_name("h1", "head")].argv
    assert head[head.index("--gpus") + 1] == '"device=0"'
    worker = pool.docker.containers[pooled.container_name("w2", "worker-1")].argv
    assert worker[worker.index("--gpus") + 1] == "device=1"
    assert sorted(pool.docker.of_session("h1")) == sorted(
        pooled.container_name("h1", part) for part in ("tunnel", "head")
    )
    assert sorted(pool.docker.of_session("w2")) == sorted(
        pooled.container_name("w2", part) for part in ("tunnel", "worker-1")
    )


def test_a_worker_on_a_card_another_session_holds_is_busy_and_starts_nothing(
    pool: Pool,
) -> None:
    from mcgyvr.sandbox import pooled

    _prepare(pool, "h1", "head", "p1")
    assert _head_on(pool, "h1", "c1", 0)["type"] == "ack"
    prepared = _prepare(pool, "w2", "worker", "p2")
    _up(pool, "w2", prepared["body"]["listen_port"], "t2")
    pool.settle()
    before = list(pool.docker.runs())

    _busy(_worker_on(pool, "w2", "c2", 0))
    _busy(_worker_on(pool, "w2", "c3", 1, 0))
    pool.settle()
    assert pool.docker.runs() == before
    assert pooled.container_name("w2", "worker-1") not in pool.docker.containers
    # refused, the session still may take a card no one holds
    ack = _worker_on(pool, "w2", "c4", 1)
    assert ack is not None and ack["type"] == "ack", ack
    _state(pool, "w2", "ready")


def test_a_head_on_a_card_another_session_holds_is_busy_and_starts_nothing(
    pool: Pool,
) -> None:
    from mcgyvr.sandbox import pooled

    prepared = _prepare(pool, "w1", "worker", "p1")
    _up(pool, "w1", prepared["body"]["listen_port"], "t1")
    assert _worker_on(pool, "w1", "c1", 1)["type"] == "ack"
    _state(pool, "w1", "ready")
    _prepare(pool, "h2", "head", "p2")

    _busy(_head_on(pool, "h2", "c2", 1))
    _busy(_head_on(pool, "h2", "c3", 0, 1))
    pool.settle()
    assert pooled.container_name("h2", "head") not in pool.docker.containers
    ack = _head_on(pool, "h2", "c4", 0)
    assert ack is not None and ack["type"] == "ack", ack
    _state(pool, "h2", "ready")


def test_a_session_is_busy_when_every_lent_card_is_held(pool: Pool) -> None:
    from mcgyvr.sandbox import pooled

    _head_and_worker(pool)
    runs = list(pool.docker.runs())
    _busy(pool.ask("session_prepare", "p3", session_id="s3", role="worker"))
    _busy(pool.ask("session_prepare", "p4", session_id="s4", role="head"))
    pool.settle()
    assert pool.docker.runs() == runs
    assert pooled.container_name("s3", "tunnel") not in pool.docker.containers


def test_stopping_one_session_leaves_the_other_running_and_frees_its_cards(
    pool: Pool,
) -> None:
    from mcgyvr.sandbox import pooled

    _head_and_worker(pool)
    pool.settle()
    since = len(pool.docker.calls)
    ack = pool.ask("session_stop", "x1", session_id="h1", reason="done")
    assert ack is not None and ack["type"] == "ack"
    _state(pool, "h1", "stopped")
    pool.settle()

    assert pool.docker.of_session("h1") == []
    removed = [
        name
        for verb, args in pool.docker.calls[since:]
        if verb == "rm"
        for name in args
    ]
    assert removed and not set(removed) & set(pool.docker.of_session("w2"))
    assert sorted(pool.docker.of_session("w2")) == sorted(
        pooled.container_name("w2", part) for part in ("tunnel", "worker-1")
    )
    assert pool.sessions.state_of("w2") == ("ready", "worker")
    assert pool.sessions.running() == ("w2",)
    pool.lease_renewed("w2", pool.renewals("w2"))  # its lease is kept up
    assert pool.sessions.state_of("w2") == ("ready", "worker")

    # card 0 is free again: a new session takes it
    _prepare(pool, "h3", "head", "p3")
    ack = _head_on(pool, "h3", "c3", 0)
    assert ack is not None and ack["type"] == "ack", ack
    _state(pool, "h3", "ready")


def test_a_failed_session_frees_its_cards_and_the_other_runs_on(pool: Pool) -> None:
    from mcgyvr.sandbox import pooled

    _head_and_worker(pool)
    pool.docker.containers[pooled.container_name("h1", "head")].state = "exited"
    _state(pool, "h1", "failed")
    pool.settle()
    assert pool.docker.of_session("h1") == []
    assert pool.sessions.state_of("w2") == ("ready", "worker")
    _prepare(pool, "h3", "head", "p3")
    ack = _head_on(pool, "h3", "c3", 0)
    assert ack is not None and ack["type"] == "ack", ack


def test_the_agent_says_it_runs_a_session_per_card() -> None:
    from mcgyvr.rig import session

    assert session.MULTI_SESSION_FEATURE == "multi_session"
    assert "multi_session" in session.FEATURES
    assert len(session.FEATURES) == len(set(session.FEATURES))


def test_a_lending_hello_names_the_feature(tmp_path: Path) -> None:
    from mcgyvr.rig import protocol, session

    offer = session.offer(
        fakes.sharing(tmp_path),
        fakes.inventory(tmp_path),
        (fakes.LAN_ADDRESS,),
        (),
    )
    assert "multi_session" in offer.features
    assert len(offer.features) <= protocol.MAX_FEATURES
