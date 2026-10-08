"""A coding plan is a ladder, and a chat plan is one unit.

Plan section 10, P5; owner, Rounds 7 and 9. Coding: a ladder per rig that
starts with the model serving coding that does the most work filled with
slots, and climbs by clear steps to a top rung, a middle rung only within the
climb budget. Chat and agent: one unit for the whole fleet, spanning every
card.

Promises, from the shipped knowledge on invented machines:

* Coding: each rig's ladder starts with a model that serves coding (which
  one: ``test_the_fast_rung_is_the_coder_that_does_the_most_work_filled_with_slots``),
  at 8k per slot, and ends with its top rung, at 32k per slot (the model's
  own context when shorter; a ladder of one rung is its own top rung, and
  says so where it cannot hold that much); each model up the ladder is a
  clear step above the one below (a copy of a rung is no step:
  ``test_a_coding_rig_puts_work_on_every_card``), and where a middle rung was
  added, a climb through every model reads at most the climb budget times
  the top rung's bytes per token. Every rung serves coding.
* Chat and agent: one serving unit in the whole plan, however many cards and
  machines, and it serves the use case.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import cli, planner, recommend
from mcgyvr.scan import Disk, Gpu, Machine, Memory, Scan, Vram

RIGS = ("192.0.2.20", "192.0.2.21")


def _scan(host: str, free_mib: tuple[int, ...]) -> Scan:
    return Scan(
        machine=Machine(id=f"machine-{host}", host=host, kernel="0.0.0-example"),
        gpus=tuple(
            Gpu(
                index=index,
                name="Example Card V",
                vram=Vram(
                    total_mib=free + 512, used_mib=512, free_mib=free, reserved_mib=0
                ),
            )
            for index, free in enumerate(free_mib)
        ),
        memory=Memory(total_gb=36.0, available_gb=32.0),
        disk=Disk(path=Path("/weights"), free_gb=500.0),
    )


SCANS = {RIGS[0]: _scan(RIGS[0], (11800, 11800)), RIGS[1]: _scan(RIGS[1], (24000,))}


def _plan(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], use_case: str
) -> dict[str, Any]:
    monkeypatch.setattr(recommend, "_scan_host", lambda host: SCANS[host])
    argv = ["recommend", "--use-case", use_case, "--users", "2", "--offline"]
    for rig in RIGS:
        argv += ["--host", rig]
    code = cli.main(argv)
    out = capsys.readouterr()
    assert code == 0, out.err
    plan: dict[str, Any] = json.loads(out.out)
    return plan


def _models() -> dict[str, planner.Model]:
    return {model.model_id: model for model in planner.library().models}


def test_a_coding_plan_is_a_ladder_per_rig(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _plan(monkeypatch, capsys, "coding")
    models = _models()
    by_name = {u["name"]: u for laid in plan["rigs"].values() for u in laid["units"]}
    for rig in RIGS:
        rungs = [by_name[n] for n in plan["ladder"] if n.startswith(f"{rig}-")]
        assert rungs
        coders = [m for m in models.values() if planner.serves(m, "coding")]
        assert all(planner.serves(models[r["model"]["id"]], "coding") for r in rungs)
        assert rungs[0]["model"]["id"] in {m.model_id for m in coders}
        if len(rungs) > 1:
            assert rungs[0]["ctx_per_slot"] == 8192
        top = rungs[-1]
        if len(rungs) > 1 or not any("only rung" in n for n in top["notes"]):
            assert top["ctx_per_slot"] == min(32768, top["model"]["context_length"])
        steps = [models[i] for i in dict.fromkeys(r["model"]["id"] for r in rungs)]
        for lower, upper in itertools.pairwise(steps):
            assert planner.clear_step("coding", lower, upper, step=planner.CLEAR_STEP)
        if len(steps) > 2:
            climb = sum(planner.token_bytes(model) for model in steps)
            assert climb <= planner.CLIMB_BUDGET * planner.token_bytes(steps[-1])


@pytest.mark.parametrize("use_case", ["chat", "agent"])
def test_a_chat_plan_is_one_unit_for_the_whole_fleet(
    use_case: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _plan(monkeypatch, capsys, use_case)
    serving = [
        u
        for laid in plan["rigs"].values()
        for u in laid["units"]
        if u["process"] == "serve"
    ]
    (unit,) = serving
    assert plan["ladder"] == [unit["name"]]
    assert planner.serves(_models()[unit["model"]["id"]], use_case)
