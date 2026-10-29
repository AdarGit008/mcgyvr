"""A lender of no card offers the head alone, and heads no pipeline.

Memory and cores serve a small model whole, never a stage of a split one. So a
rig that lends no card its sessions can run offers the head role alone, even
when its owner allows the worker role too; a ``session_prepare`` as a worker
is refused as not capable, and a ``head_start`` that hands it rpc devices,
which would make it the head of a pipeline, is refused the same way and starts
nothing. A system with no session host yet (macOS and Windows, until the
native session host lands) offers no session role at all, and its offer
names none. A head this rig runs is held to what it lends: its container to
the memory and cores lent, llama-server to that many threads.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.hubwire import LEND_FLOOR_MB, RESOURCE_RAM
from tests import rig_pool_fakes as fakes
from tests.machine_shapes import HostShape, host_reading
from tests.rig_pool_fakes import Pool, make_pool, prepared

RAM_FLOOR = LEND_FLOOR_MB[RESOURCE_RAM]


@pytest.fixture
def cardless(tmp_path: Path) -> Iterator[Pool]:
    made = make_pool(tmp_path, cards=(), ram_mb=RAM_FLOOR, cpu_cores=4)
    yield made
    made.sessions.close()


def _refused(answer: dict[str, Any] | None, code: str) -> None:
    assert answer is not None and answer["type"] == "error", answer
    assert answer["body"]["code"] == code, answer


def test_a_lender_of_no_card_offers_the_head_alone(tmp_path: Path) -> None:
    from mcgyvr.rig import session

    report = fakes.report()
    share = fakes.sharing(tmp_path, cards=(), ram_mb=RAM_FLOOR, cpu_cores=4)
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


def test_a_head_is_held_to_the_memory_and_cores_lent() -> None:
    import dataclasses
    from pathlib import PurePosixPath

    from mcgyvr.rig import pooled, sharing

    spec = pooled.HeadSpec(
        session_id="s",
        image="engine:rpc",
        binary="/app/llama-server",
        gpus=(0,),
        models_dir=Path(PurePosixPath("/srv/models")),
        model="m.gguf",
        name="m.gguf",
        ctx=256,
        n_gpu_layers=99,
        devices=("CUDA0",),
        tensor_split=(1,),
        rpc=(),
        bind="10.0.0.2",
        memory_mb=8192,
    )
    owner = pooled.Owner(uid=1000, gid=1000, agent_pid=1)
    plain = pooled.head_argv(spec, owner)
    assert "--cpus" not in plain and "--threads" not in plain
    held = pooled.head_argv(dataclasses.replace(spec, cpus=3), owner)
    image = held.index("engine:rpc")
    assert held[held.index("--cpus") + 1] == "3" and held.index("--cpus") < image
    assert held[held.index("--threads") + 1] == "3" and held.index("--threads") > image
    # With nothing lent beside a head, its container keeps the default cap.
    assert sharing.Sharing().head_limits(fakes.report()) == (
        sharing.DEFAULT_CONTAINER_MB,
        None,
    )


def test_a_head_runs_under_the_lend_as_advertised_never_past_the_machine(
    tmp_path: Path,
) -> None:
    from mcgyvr import hubwire
    from mcgyvr.rig import hardware, sharing

    machine = HostShape(
        label="linux-lender",
        system="linux",
        machine_id="0123456789abcdef0123456789abcdf5",
        memory_mib=RAM_FLOOR * 8,
        available_mib=RAM_FLOOR * 6,
        cpu_model="Example CPU L12",
        cores=6,
        threads=12,
        version="6.1-example",
    )
    reading = host_reading(machine)
    report = hardware.read(reader=lambda: reading)
    greedy = fakes.sharing(tmp_path, cards=(), ram_mb=10**6, cpu_cores=999)
    memory, cpus = greedy.head_limits(report)
    assert memory == report.ram_total_mb - sharing.RAM_HEADROOM_MB
    assert cpus == 12 - sharing.CORES_KEPT == 11
    lent = {r.kind: r for r in greedy.lent(report)}
    assert (memory, cpus) == (
        lent[hubwire.RESOURCE_RAM].total_mb,
        lent[hubwire.RESOURCE_CPU].cores,
    )
    capped = fakes.sharing(tmp_path, cards=(), ram_mb=10**6, max_ram_mb=RAM_FLOOR)
    assert capped.head_limits(report)[0] == RAM_FLOOR


def test_a_head_start_plans_the_head_under_the_lend_as_advertised(
    tmp_path: Path,
) -> None:
    from mcgyvr.rig import sharing

    greedy = make_pool(tmp_path, cards=(0,), ram_mb=10**6, cpu_cores=999)
    try:
        prepared(greedy, role="head")
        body = fakes.tunnel_up_body(address=f"{fakes.PEER}/24")
        body["peers"][0]["allowed_ips"] = [f"{fakes.SELF}/32"]
        greedy.up("t1", **body)
        answer = greedy.ask(
            "head_start",
            "h1",
            session_id="s1",
            model={"name": fakes.MODEL},
            ctx=4096,
            devices=[{"kind": "local", "card_index": 0}],
            tensor_split=[1],
        )
        assert answer is not None and answer["type"] == "ack", answer
        greedy.settle()
        from mcgyvr.rig import pooled

        head = greedy.docker.containers[pooled.container_name("s1", "head")].argv
        cores = fakes.REPORT_THREADS - sharing.CORES_KEPT
        assert head[head.index("--cpus") + 1] == str(cores)
        assert head[head.index("--threads") + 1] == str(cores)
        memory = fakes.report().ram_total_mb - sharing.RAM_HEADROOM_MB
        assert head[head.index("--memory") + 1] == f"{memory}m"
    finally:
        greedy.sessions.close()
