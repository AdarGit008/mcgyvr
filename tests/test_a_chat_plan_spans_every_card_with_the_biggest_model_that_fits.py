"""A chat (or agent) plan is one unit spanning every card, the biggest model that fits.

Owner, Round 7 (2026-10-07): "chat/agent: least context 8k per user (more
whenever it fits). With multiple GPUs / machines: PIPELINE PARALLEL — one
unit spanning them, the BIGGEST model that fits across all of them (not one
unit per rig)." Orchestrator call, same round: a model that fits wholly on
the card(s), with no experts in RAM, ranks before one that does not (RAM and
CPU units are for sleepers), then the larger file.

Promises, over invented machines and the shipped knowledge:

* Several cards of one machine: one unit holds them all, split by layer (the
  pipeline split), sized by the product's own sharding.
* Several machines reached at private addresses: one unit spans every card of
  every machine, its head on the first ``--host`` and an RPC worker on each
  other one; only the head downloads the weights.
* Several machines reached by name: the product does not guess a name into an
  address, so the unit spans the first machine's cards and the plan says why
  it does not span the others.
* Between two models that fit, one that fits wholly on the cards is planned
  before a larger one that needs RAM for its experts.
* Every unit gets at least 8192 tokens per user.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import cli, recommend
from mcgyvr.scan import Disk, Gpu, Machine, Memory, Scan, Vram

#: Invented machines at documentation addresses (RFC 5737), and by name.
NEAR, FAR = "192.0.2.10", "192.0.2.11"
NAMED = ("rig-d.invalid", "rig-e.invalid")


def _scan(host: str, free_mib: tuple[int, ...], ram_gb: float = 0.0) -> Scan:
    return Scan(
        machine=Machine(id=f"machine-{host}", host=host, kernel="0.0.0-example"),
        gpus=tuple(
            Gpu(
                index=index,
                name="Example Card Y",
                vram=Vram(
                    total_mib=free + 512, used_mib=512, free_mib=free, reserved_mib=0
                ),
            )
            for index, free in enumerate(free_mib)
        ),
        memory=Memory(total_gb=ram_gb + 4, available_gb=ram_gb),
        disk=Disk(path=Path("/weights"), free_gb=500.0),
    )


def _plan(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    scans: dict[str, Scan],
    *,
    users: int = 1,
    use_case: str = "chat",
) -> dict[str, Any]:
    monkeypatch.setattr(recommend, "_scan_host", lambda host: scans[host])
    argv = ["recommend", "--use-case", use_case, "--users", str(users), "--offline"]
    for host in scans:
        argv += ["--host", host]
    code = cli.main(argv)
    out = capsys.readouterr()
    assert code == 0, out.err
    plan: dict[str, Any] = json.loads(out.out)
    return plan


def _units(plan: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [(rig, u) for rig, laid in plan["rigs"].items() for u in laid["units"]]


@pytest.mark.parametrize("use_case", ["chat", "agent"])
def test_the_cards_of_one_machine_are_one_unit_split_by_layer(
    use_case: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _plan(
        monkeypatch, capsys, {NEAR: _scan(NEAR, (7000, 7000))}, use_case=use_case
    )

    ((rig, unit),) = _units(plan)
    assert rig == NEAR
    assert unit["cards"] == [0, 1]
    assert unit["args"]["--split-mode"] == "layer"
    assert unit["ctx_per_slot"] >= 8192


def test_machines_at_private_addresses_are_one_unit_with_an_rpc_worker(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scans = {NEAR: _scan(NEAR, (7000,)), FAR: _scan(FAR, (7000,))}

    plan = _plan(monkeypatch, capsys, scans)

    units = _units(plan)
    heads = [(rig, u) for rig, u in units if u["process"] == "serve"]
    workers = [(rig, u) for rig, u in units if u["process"] == "rpc"]
    ((head_rig, head),) = heads
    ((worker_rig, worker),) = workers
    assert (head_rig, worker_rig) == (NEAR, FAR)
    assert worker["head"] == head["name"]
    assert {(s["rig"], s["card"]) for s in head["shards"]} == {(NEAR, 0), (FAR, 0)}
    assert head["download"]["bytes"] > 0
    assert worker["download"]["bytes"] == 0
    assert plan["ladder"] == [head["name"]]
    assert head["ctx_per_slot"] >= 8192


def test_machines_reached_by_name_span_the_first_and_the_plan_says_why(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first, second = NAMED
    scans = {first: _scan(first, (7000, 7000)), second: _scan(second, (7000,))}

    plan = _plan(monkeypatch, capsys, scans)

    ((rig, unit),) = _units(plan)
    assert rig == first
    assert unit["cards"] == [0, 1]
    assert any("IPv4" in note for note in unit["notes"]), unit["notes"]


def test_a_model_wholly_on_the_cards_ranks_before_a_larger_one_needing_ram(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _plan(monkeypatch, capsys, {NEAR: _scan(NEAR, (11800,), ram_gb=48.0)})

    ((_rig, unit),) = _units(plan)
    assert unit["n_cpu_moe"] == 0
    assert unit["fit"]["ram_gib"] == 0
    assert unit["model"]["id"] == "Qwen/Qwen3-14B"


@pytest.mark.parametrize("users", [1, 2, 4])
def test_every_user_gets_8k_or_more(
    users: int, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _plan(monkeypatch, capsys, {NEAR: _scan(NEAR, (11800, 11800))}, users=users)
    ((_rig, unit),) = _units(plan)
    assert unit["slots"] == users
    assert unit["ctx_per_slot"] >= 8192
