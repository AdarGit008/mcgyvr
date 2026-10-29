"""A lender of no card offers the head alone, and heads no pipeline.

Memory and cores serve a small model whole, never a stage of a split one. So a
rig that lends no card its sessions can run offers the head role alone, even
when its owner allows the worker role too; a ``session_prepare`` as a worker
is refused as not capable, and a ``head_start`` that hands it rpc devices,
which would make it the head of a pipeline, is refused the same way and starts
nothing. A system with no session host yet (macOS and Windows, until the
native session host lands) offers no session role at all, and its offer
names none.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes
from tests.rig_pool_fakes import Pool, make_pool, prepared


@pytest.fixture
def cardless(tmp_path: Path) -> Iterator[Pool]:
    made = make_pool(tmp_path, cards=(), ram_mb=8192, cpu_cores=4)
    yield made
    made.sessions.close()


def _refused(answer: dict[str, Any] | None, code: str) -> None:
    assert answer is not None and answer["type"] == "error", answer
    assert answer["body"]["code"] == code, answer


def test_a_lender_of_no_card_offers_the_head_alone(tmp_path: Path) -> None:
    from mcgyvr.rig import session

    report = fakes.report()
    share = fakes.sharing(tmp_path, cards=(), ram_mb=8192, cpu_cores=4)
    assert share.offered_roles() == ("head", "worker")
    assert share.session_roles(report) == ("head",)
    held = fakes.inventory(tmp_path)
    offer = session.offer(share, held, (fakes.LAN_ADDRESS,), (), report)
    assert offer.roles == ("head",) and offer.models == held.models
    # A rig that lends a card its sessions run on keeps both roles.
    assert fakes.sharing(tmp_path).session_roles(report) == ("head", "worker")


def test_a_lender_of_no_card_is_never_prepared_as_a_worker(cardless: Pool) -> None:
    _refused(
        cardless.ask("session_prepare", "p1", session_id="s1", role="worker"),
        "not_capable",
    )
    assert cardless.docker.runs() == []


def test_a_lender_of_no_card_heads_no_pipeline(cardless: Pool) -> None:
    prepared(cardless, role="head")
    body = fakes.tunnel_up_body(address=f"{fakes.PEER}/24")
    body["peers"][0]["allowed_ips"] = [f"{fakes.SELF}/32"]
    cardless.up("t1", **body)
    answer = cardless.ask(
        "head_start",
        "h1",
        session_id="s1",
        model={"name": fakes.MODEL},
        ctx=4096,
        devices=[{"kind": "rpc", "host": fakes.SELF, "port": 50052}],
        tensor_split=[1],
    )
    _refused(answer, "not_capable")
    cardless.settle()
    assert len(cardless.docker.runs()) == 1  # the tunnel alone


@pytest.mark.parametrize("system", ["darwin", "windows"])
def test_a_system_with_no_session_host_offers_no_role(
    tmp_path: Path, system: str
) -> None:
    import dataclasses

    from mcgyvr.rig import session
    from mcgyvr.scan import Host

    report = dataclasses.replace(
        fakes.report(), host=Host(os=system, arch="arm64", version="1")
    )
    share = fakes.sharing(tmp_path)
    assert share.session_roles(report) == ()
    offer = session.offer(share, fakes.inventory(tmp_path), (), (), report)
    assert offer.roles == () and offer.runtime is None
    assert share.lendable(report).lent == ()
