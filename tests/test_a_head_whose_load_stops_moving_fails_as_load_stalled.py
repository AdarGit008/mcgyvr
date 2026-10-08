"""A head whose load stops moving fails as ``load_stalled``.

A head that loads its layers onto workers on other rigs sends them the
weights over the session's tunnel, and says nothing of how far it is until it
is ready. A path that carries small packets and loses large ones leaves the
worker answering every ping while the weights stand still, so the watch of
the workers sees a living peer and the head would wait out its whole load.
So while it loads, the head also counts what the tunnel sends its workers
(WireGuard counts every byte): a load that has not sent them
``LOAD_STALL_BYTES`` in the session's stall time fails as ``load_stalled``,
naming how little moved, and is torn down. A load that goes quiet for less
than that and moves again goes on — a head reads its own layers from disk
without sending a byte — and says, once loaded, the longest it took to move
that much, so the time can be set from what real loads do. A head that is
ready is never judged so: an idle unit sends nothing. A head alone on one rig
has no tunnel to count.
"""

from __future__ import annotations

import dataclasses
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


def _timing(pool: Pool, **changes: float) -> None:
    pool.sessions.timing = dataclasses.replace(pool.sessions.timing, **changes)


def _head(pool: Pool, *, alone: bool = False) -> None:
    prepared(pool, role="head")
    devices = [{"kind": "local", "card_index": 0}]
    if not alone:
        body = fakes.tunnel_up_body(address=f"{fakes.PEER}/24")
        body["peers"][0]["allowed_ips"] = [f"{fakes.SELF}/32"]
        pool.up("t1", **body)
        devices.append({"kind": "rpc", "host": fakes.SELF, "port": 50052})
    ack = pool.ask(
        "head_start",
        "h1",
        session_id="s1",
        model={"name": fakes.MODEL},
        ctx=4096,
        devices=devices,
        tensor_split=[1] * len(devices),
    )
    assert ack is not None and ack["type"] == "ack"


def _failed(pool: Pool) -> list[dict[str, object]]:
    return [
        f["body"]
        for f in pool.box.of_type("session_status")
        if f["body"]["state"] == "failed"
    ]


def test_a_load_whose_worker_answers_pings_but_takes_no_weights_fails_as_stalled(
    pool: Pool,
) -> None:
    _timing(pool, stall_s=0.2, load_s=60.0)
    pool.health[:] = ["loading"]  # the head never finishes loading on its own
    started = time.monotonic()
    _head(pool)  # the worker answers every ping; the bytes sent it stand still
    pool.wait_for("session_status", "failed")
    took = time.monotonic() - started
    failed = pool.box.of_type("session_status")[-1]["body"]
    assert failed["error_code"] == "load_stalled" and failed["role"] == "head"
    assert "0.2 s" in failed["log_excerpt"]
    assert took < pool.sessions.timing.load_s / 10
    assert pool.docker.peer_rx > 0  # it was heard from all along
    assert pool.docker.of_session("s1") == []


def test_a_load_that_goes_quiet_for_less_than_the_stall_time_and_moves_again_goes_on(
    pool: Pool,
) -> None:
    from mcgyvr.rig import session as rs

    _timing(pool, stall_s=1.0, load_s=60.0)
    pool.health[:] = ["loading"]
    _head(pool)
    pool.wait_for("session_status", "loading")
    time.sleep(0.3)  # the head reads its own layers: nothing crosses the tunnel
    until = time.monotonic() + 1.5  # then longer than the stall time, moving
    while time.monotonic() < until:
        pool.docker.peer_tx += rs.LOAD_STALL_BYTES
        time.sleep(0.05)
    assert not _failed(pool)
    pool.health[:] = ["ok"]
    pool.wait_for("session_status", "ready")
    assert not _failed(pool)
    said = [line for line in pool.logged if "s1" in line and "longest" in line]
    assert len(said) == 1, pool.logged


def test_a_ready_unit_that_goes_idle_is_never_stalled(pool: Pool) -> None:
    _timing(pool, stall_s=0.2)
    _head(pool)
    pool.wait_for("session_status", "ready")
    time.sleep(pool.sessions.timing.stall_s * 4)  # nothing is sent the worker
    assert pool.sessions.state_of("s1") == ("ready", "head")
    assert not _failed(pool)


def test_a_head_alone_on_one_rig_has_no_tunnel_to_stall(pool: Pool) -> None:
    _timing(pool, stall_s=0.2, load_s=60.0)
    pool.health[:] = ["loading"]
    _head(pool, alone=True)
    pool.wait_for("session_status", "loading")
    time.sleep(pool.sessions.timing.stall_s * 4)
    assert not _failed(pool)
    pool.health[:] = ["ok"]
    pool.wait_for("session_status", "ready")
    assert not [line for line in pool.logged if "longest" in line]


def test_the_sent_reading_takes_only_well_formed_lines() -> None:
    from mcgyvr.rig import pooled

    said = (
        f"{fakes.PEER_KEY}\t1024\t2048\n"
        f"{fakes.KEY}\t1\t-5\n"
        "garbage\n"
        f"{'C' * 42}Q=\t12\t\n"
        f"{fakes.KEY}\t1\t99999999999999999999999\n"
    )
    assert pooled.read_sent(said) == {fakes.PEER_KEY: 2048}
