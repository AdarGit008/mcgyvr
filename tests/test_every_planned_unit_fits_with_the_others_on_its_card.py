"""Every planned unit fits with the others on its card.

Owner, Round 2 (2026-10-07): the plan is "sized with the product's existing
serving sizer (serving.fit, sharding.py, vramfit: several models per card,
multi-card split, MoE experts in RAM), not recommend's own _fits". Plan
section 10, P5: over every invented machine shape.

Promises, for every shape of ``tests/machine_shapes.py`` and every text use
case, from the shipped knowledge, offline:

* The plan is printed, or refused because nothing fits; a refusal names why,
  and a shape with a card the product reads and room on it is planned.
* Every unit is on cards the scan read, and on each card the units' card
  figures (the serving sizer's own) sum to no more than what the scan read
  free there.
* The units of a rig hold together the way ``mcgyvr emit`` checks them
  (:func:`mcgyvr.serving.hold_together`): the card per card, host memory per
  host.
"""

from __future__ import annotations

import dataclasses
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import cli, planner, recommend, serving
from mcgyvr.scan import Disk, Memory
from tests.machine_shapes import Shape, scan, shapes

USE_CASES = ("chat", "agent", "coding")
#: Invented host memory and disk every shape is given: shapes say neither.
RAM_GB = 48.0
DISK_GB = 500.0
USERS = 2


def _scanned(machine: Shape) -> Any:
    return dataclasses.replace(
        scan(machine),
        memory=Memory(total_gb=RAM_GB + 16, available_gb=RAM_GB),
        disk=Disk(path=Path("/weights"), free_gb=DISK_GB),
    )


@pytest.mark.parametrize("use_case", USE_CASES)
@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_every_planned_unit_fits_with_the_others_on_its_card(
    machine: Shape,
    use_case: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    measured = _scanned(machine)
    monkeypatch.setattr(recommend, "_scan_host", lambda host: measured)

    code = cli.main(
        [
            "recommend",
            "--use-case",
            use_case,
            "--users",
            str(USERS),
            "--host",
            machine.host,
            "--offline",
        ]
    )
    out = capsys.readouterr()

    roomy = any(
        serving.fit(
            dataclasses.replace(measured, gpus=(gpu,)),
            planner.spec_of(model),
            engine="llama.cpp",
            width=planner.least_width(use_case, USERS),
            ctx_per_slot=planner.least_ctx(use_case, model),
        ).fits
        for gpu in measured.gpus
        for model in planner.library().models
    )
    if code != 0:
        assert out.err.strip(), "a refusal says why"
        assert not roomy, out.err
        return
    plan = json.loads(out.out)
    laid = plan["rigs"][machine.host]
    free = {card["index"]: card["free_mib"] for card in laid["measured"]["cards"]}
    on_card: dict[int, float] = defaultdict(float)
    for unit in laid["units"]:
        assert set(unit["cards"]) <= set(free), unit["cards"]
        for card in unit["cards"]:
            on_card[card] += unit["fit"]["vram_gib"]
    for card, gib in on_card.items():
        assert gib * 1024 <= free[card], (card, gib, free[card])
    units = planner.units_of(plan, {machine.host: measured})
    assert len(units) == len(laid["units"])
    serving.hold_together(units, {machine.host: measured})
