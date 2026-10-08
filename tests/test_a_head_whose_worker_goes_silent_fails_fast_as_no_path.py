"""A head whose worker goes silent over the tunnel fails fast, as ``no_path``.

A head that loads its layers onto a worker on another rig sits in ``loading``
while the weights cross the tunnel; when that rig dies, or its tunnel does,
the engine's connection to it just stops — no reset ever arrives — and the
head would wait out its whole load timeout. So while it starts, loads, and
serves, the head watches each worker it was given: a worker heard from over
the tunnel (WireGuard counts every byte it sends) is alive; a worker that
has been quiet since the last look is asked (one ping over the tunnel); a
worker not heard from for the session's silence limit is lost, and the
session fails with ``no_path`` (the hub's code for a peer no path reaches),
naming the worker's tunnel address, and is torn down. A worker that keeps
answering is never declared lost, and what the tunnel prints that does not
read is silence, never life.
"""

from __future__ import annotations

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


def _head(pool: Pool) -> None:
    prepared(pool, role="head")
    body = fakes.tunnel_up_body(address=f"{fakes.PEER}/24")
    body["peers"][0]["allowed_ips"] = [f"{fakes.SELF}/32"]
    pool.up("t1", **body)
    ack = pool.ask(
        "head_start",
        "h1",
        session_id="s1",
        model={"name": fakes.MODEL},
        ctx=4096,
        devices=[
            {"kind": "local", "card_index": 0},
            {"kind": "rpc", "host": fakes.SELF, "port": 50052},
        ],
        tensor_split=[1, 1],
    )
    assert ack is not None and ack["type"] == "ack"


def test_a_worker_that_goes_silent_while_the_head_loads_fails_it_fast(
    pool: Pool,
) -> None:
    from mcgyvr.rig import pooled

    pool.health[:] = ["loading"]  # the head never finishes loading on its own
    pool.docker.peer_silent = True
    started = time.monotonic()
    _head(pool)
    pool.wait_for("session_status", "failed")
    took = time.monotonic() - started
    failed = pool.box.of_type("session_status")[-1]["body"]
    assert failed["error_code"] == "no_path" and failed["role"] == "head"
    assert fakes.SELF in failed["log_excerpt"]
    assert took < pool.sessions.timing.load_s
    assert pool.docker.of_session("s1") == []
    poked = [s for s in pool.docker.scripts if s[1] == pooled.TRANSFER_SCRIPT]
    assert poked and any(fakes.SELF in call[2] for call in poked)


def test_a_worker_that_goes_silent_after_the_head_is_ready_fails_it(
    pool: Pool,
) -> None:
    _head(pool)
    pool.wait_for("session_status", "ready")
    pool.docker.peer_silent = True
    pool.wait_for("session_status", "failed")
    failed = pool.box.of_type("session_status")[-1]["body"]
    assert failed["error_code"] == "no_path"
    assert pool.docker.of_session("s1") == []


def test_a_worker_that_keeps_answering_is_never_lost(pool: Pool) -> None:
    _head(pool)
    pool.wait_for("session_status", "ready")
    time.sleep(pool.sessions.timing.peer_lost_s * 3)
    assert pool.sessions.state_of("s1") == ("ready", "head")
    assert not [
        f for f in pool.box.of_type("session_status") if f["body"]["state"] == "failed"
    ]


def test_what_the_tunnel_prints_that_does_not_read_is_silence(pool: Pool) -> None:
    pool.docker.transfer_said = "not\ta transfer line\n" + "x" * 5000
    _head(pool)
    pool.wait_for("session_status", "failed")
    assert pool.box.of_type("session_status")[-1]["body"]["error_code"] == ("no_path")


def test_the_transfer_reading_takes_only_well_formed_lines() -> None:
    from mcgyvr.rig import pooled

    said = (
        f"{fakes.PEER_KEY}\t1024\t2048\n"
        f"{fakes.KEY}\t-5\t1\n"
        "garbage\n"
        f"{'C' * 42}Q=\t12\t\n"
        f"{fakes.KEY}\t99999999999999999999999\t1\n"
    )
    assert pooled.read_transfer(said) == {fakes.PEER_KEY: 1024}
