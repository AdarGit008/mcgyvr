"""A ``tunnel_report`` is sent only once the session is up.

The report tells the hub the tunnel is up; the hub then starts the session's
workers or head, and may ask where the session stands. So by the time the
report is on the wire the session must already be ``tunnel_up``: a report
sent first, with the state moved after it, left a window in which this rig
said ``prepared`` of a tunnel it had just reported up (and a test reading the
state on the report's arrival failed now and then). A peer no path reaches
is reported all the same, and the session fails as ``no_path`` — it is never
``tunnel_up``.
"""

from __future__ import annotations

import ipaddress
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes
from tests.rig_pool_fakes import Pool, make_pool

#: A public address, written as a number so that no real machine is named.
REFLEXIVE = str(ipaddress.IPv4Address(2**31 + 7))


@pytest.fixture
def pool_and_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Pool, list[tuple[str, str | None]]]]:
    """A pool whose outbox notes the session's state as each report is sent."""
    states: list[tuple[str, str | None]] = []
    made: list[Pool] = []
    put = fakes.Box.put

    def noting(box: fakes.Box, frame: str, timeout: float | None = None) -> bool:
        if json.loads(frame)["type"] == "tunnel_report" and made:
            states.append(made[0].sessions.state_of("s1"))
        return put(box, frame, timeout)

    monkeypatch.setattr(fakes.Box, "put", noting)
    made.append(make_pool(tmp_path))
    yield made[0], states
    made[0].sessions.close()


def _up(pool: Pool, endpoints: list[dict[str, Any]]) -> dict[str, Any]:
    assert pool.ask("session_prepare", "p1", session_id="s1", role="worker") is None
    pool.wait_for("session_prepared")
    body = fakes.tunnel_up_body()
    body["peers"][0]["endpoints"] = endpoints
    return pool.up("t1", **body)


def test_the_session_is_tunnel_up_when_its_report_is_sent(
    pool_and_states: tuple[Pool, list[tuple[str, str | None]]],
) -> None:
    pool, states = pool_and_states
    lan = {"host": fakes.PEER_ADDRESS, "port": 51820, "kind": "lan"}
    report = _up(pool, [lan])
    assert report["body"]["peers"][0]["path"] == "lan"
    assert states == [("tunnel_up", "worker")]


def test_a_session_no_path_reaches_is_reported_and_never_tunnel_up(
    pool_and_states: tuple[Pool, list[tuple[str, str | None]]],
) -> None:
    pool, states = pool_and_states
    pool.docker.answering = set()
    reflexive = {"host": REFLEXIVE, "port": 40000, "kind": "reflexive"}
    report = _up(pool, [reflexive])
    assert report["body"]["peers"] == [{"rig_id": "rig-peer", "path": "none"}]
    pool.wait_for("session_status", "failed")
    assert states == [("prepared", "worker")]
    assert pool.box.of_type("session_status")[-1]["body"]["error_code"] == "no_path"
