"""The fast rung is the coder that does the most work once its card is filled.

Owner, Round 9: the "fastest" rung is the one that gives the most total output
once the card is filled with parallel slots (throughput), not the one that is
fastest per token for one user. On a 12 GB card that is the 7B coder with
about eleven slots, not DeepSeek-Coder-V2-Lite at one slot of 8k with a q8_0
cache.

A unit's work is estimated from what the plan already estimates a rung's time
by: the bytes one token reads (:func:`mcgyvr.planner.token_bytes`). A decode
step of a filled unit serves every slot for one read of its weights, so the
unit's output is its slots over its bytes per token.

Promises, from the shipped knowledge on invented machines:

* On one 12 GB card the fast rung is the 7B coder, at 8k per slot and many
  slots; DeepSeek-Coder-V2-Lite is not the fast rung.
* On every shape, the fast rung's model is the coder with the most slots over
  bytes per token on its card, alone there at 8k with its model wholly on
  the card.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import cli, planner, recommend, serving
from mcgyvr.scan import Disk, Gpu, Machine, Memory, Scan, Vram

#: Invented machines: one 12 GB card; two 12 GB cards and a 6 GB card; one
#: 24 GB card; and two machines, one with two 12 GB cards, one with a 6 GB card.
SHAPES: dict[str, dict[str, tuple[int, ...]]] = {
    "1x12": {"rig-a.invalid": (11800,)},
    "2x12+6": {"rig-b.invalid": (11800, 11800, 5800)},
    "1x24": {"rig-c.invalid": (24000,)},
    "2x12|6": {"rig-d.invalid": (11800, 11800), "rig-e.invalid": (5800,)},
}


def _scan(host: str, free_mib: tuple[int, ...]) -> Scan:
    return Scan(
        machine=Machine(id=f"machine-{host}", host=host, kernel="0.0.0-example"),
        gpus=tuple(
            Gpu(
                index=index,
                name="Example Card X",
                vram=Vram(
                    total_mib=free + 512, used_mib=512, free_mib=free, reserved_mib=0
                ),
            )
            for index, free in enumerate(free_mib)
        ),
        memory=Memory(total_gb=68.0, available_gb=64.0),
        disk=Disk(path=Path("/weights"), free_gb=500.0),
    )


def _plan(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    rigs: dict[str, tuple[int, ...]],
) -> dict[str, Any]:
    scans = {host: _scan(host, free) for host, free in rigs.items()}
    monkeypatch.setattr(recommend, "_scan_host", lambda host: scans[host])
    argv = ["recommend", "--use-case", "coding", "--users", "1", "--offline"]
    for host in rigs:
        argv += ["--host", host]
    code = cli.main(argv)
    out = capsys.readouterr()
    assert code == 0, out.err
    plan: dict[str, Any] = json.loads(out.out)
    return plan


def _models() -> dict[str, planner.Model]:
    return {model.model_id: model for model in planner.library().models}


def _first_rungs(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Each rig's first rung, as the plan's ladder lists them."""
    first: dict[str, dict[str, Any]] = {}
    for rig, laid in plan["rigs"].items():
        names = {unit["name"]: unit for unit in laid["units"]}
        on_rig = [names[name] for name in plan["ladder"] if name in names]
        if on_rig:
            first[rig] = on_rig[0]
    return first


def test_on_one_12_gb_card_the_fast_rung_is_the_7b_coder_with_many_slots(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _plan(monkeypatch, capsys, SHAPES["1x12"])

    fast = _first_rungs(plan)["rig-a.invalid"]
    assert fast["model"]["id"] == "Qwen/Qwen2.5-Coder-7B-Instruct"
    assert fast["ctx_per_slot"] == 8192
    assert fast["kv_cache"] == {"k": "f16", "v": "f16"}
    assert fast["slots"] >= 8


def _most_slots(card: Scan, model: planner.Model, ctx: int) -> int:
    """The most slots ``model`` holds wholly on ``card`` at ``ctx`` per slot,
    with the first KV cache type that holds one."""
    for kv in planner.KV_TYPES:
        spec = planner.spec_of(model, kv=kv)
        widest = 0
        for width in range(1, serving.MAX_WIDTH + 1):
            fit = serving.fit(
                card, spec, engine="llama.cpp", width=width, ctx_per_slot=ctx
            )
            if not fit.fits or fit.ram_gb:
                break
            widest = width
        if widest:
            return widest
    return 0


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_the_fast_rung_is_the_coder_with_the_most_slots_over_bytes_per_token(
    shape: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rigs = SHAPES[shape]
    plan = _plan(monkeypatch, capsys, rigs)
    models = _models()
    coders = [m for m in models.values() if planner.serves(m, "coding")]

    for rig, fast in _first_rungs(plan).items():
        scan = _scan(rig, rigs[rig])
        (index,) = fast["cards"]
        (gpu,) = [g for g in scan.gpus if g.index == index]
        card = dataclasses.replace(scan, gpus=(gpu,))
        work = {
            m.model_id: _most_slots(card, m, min(8192, m.context_length))
            / planner.token_bytes(m)
            for m in coders
        }
        assert work[fast["model"]["id"]] == max(work.values()), (rig, work)
