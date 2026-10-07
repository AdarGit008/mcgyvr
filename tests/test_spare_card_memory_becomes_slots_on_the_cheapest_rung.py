"""Spare card memory becomes slots on the cheapest rung.

Plan section 6.1, step 3: "fill: while a card has room, add a slot to the
lowest always-on rung on it, if fit() holds and no expert block moves".
Owner, Round 7: "start with the fastest model good enough to be useful, filled
with slots". Plan section 10, P5: over every invented machine shape.

Promises, for every shape of ``tests/machine_shapes.py`` a coding ladder is
planned on, from the shipped knowledge:

* The cheapest rung has as many slots as fit beside the other awake units on
  its card: one more does not fit, or moves an expert block off the card, or
  is past the widest a unit is sized at.
* Every other awake rung has one slot.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import cli, planner, recommend, serving
from mcgyvr.scan import Disk, Memory
from tests.machine_shapes import Shape, scan, shapes


def _scanned(machine: Shape) -> Any:
    return dataclasses.replace(
        scan(machine),
        memory=Memory(total_gb=64.0, available_gb=48.0),
        disk=Disk(path=Path("/weights"), free_gb=500.0),
    )


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_spare_card_memory_becomes_slots_on_the_cheapest_rung(
    machine: Shape,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    measured = _scanned(machine)
    monkeypatch.setattr(recommend, "_scan_host", lambda host: measured)
    code = cli.main(
        [
            "recommend",
            "--use-case",
            "coding",
            "--users",
            "1",
            "--host",
            machine.host,
            "--offline",
        ]
    )
    out = capsys.readouterr()
    if code != 0:
        pytest.skip(f"no coding ladder fits this shape: {out.err.strip()[:120]}")
    plan = json.loads(out.out)
    by_name = {u["name"]: u for u in plan["rigs"][machine.host]["units"]}
    rungs = [by_name[name] for name in plan["ladder"]]
    cheapest, *others = rungs
    for rung in others:
        if rung["role"] == "always-on":
            assert rung["slots"] == 1, rung["name"]

    (card,) = cheapest["cards"]
    beside = sum(
        u["fit"]["vram_gib"]
        for u in by_name.values()
        if u is not cheapest and u["role"] == "always-on" and card in u["cards"]
    )
    if cheapest["slots"] >= serving.MAX_WIDTH:
        return
    (gpu,) = [g for g in measured.gpus if g.index == card]
    left = gpu.vram.free_mib - int(beside * 1024 + 0.999)
    one_card = dataclasses.replace(
        measured,
        gpus=(
            dataclasses.replace(gpu, vram=dataclasses.replace(gpu.vram, free_mib=left)),
        ),
    )
    model = {m.label: m for m in planner.library().models}[
        f"{cheapest['model']['id']} {cheapest['model']['quant']}"
    ]
    wider = serving.fit(
        one_card,
        planner.spec_of(model, kv=cheapest["kv_cache"]["k"]),
        engine="llama.cpp",
        width=cheapest["slots"] + 1,
        ctx_per_slot=cheapest["ctx_per_slot"],
    )
    assert not wider.fits or wider.ram_gb > 0, (cheapest["slots"], wider.why)
