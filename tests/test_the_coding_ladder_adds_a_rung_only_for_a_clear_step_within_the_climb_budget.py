"""The coding ladder adds a rung only for a clear step, within the climb budget.

Owner, Round 7 (approved rule): "start with the fastest model good enough to
be useful, filled with slots. Add a bigger rung only when it is a CLEAR
quality step up (not a near-copy of the rung below). Stop adding rungs by a
TIME BUDGET: a task that climbs all the way up must finish within ~2x the time
the top rung alone would take; a middle rung that pushes past that is left
out." The strong RAM+CPU unit sleeps and swaps; ``--priority throughput``
drops the sleeper.

Promises, over invented dense models on an invented machine:

* The first rung is the fastest model; the top is the strongest that fits
  (no board scores them here: the largest).
* A model that is a near-copy of the rung below (a file less than
  ``--clear-step`` times as large) is not a rung.
* A middle rung is added cheapest first while a climb through every rung reads
  no more than ``--climb-budget`` times the top rung's own bytes per token.
* A top rung that does not fit awake beside the others, and fits alone,
  sleeps until needed and swaps with the awake rungs on its card; the plan
  turns the manager on and its sample measures one swap. With ``--priority
  throughput`` no rung sleeps: the top is the strongest that fits awake.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import cli, planner, recommend
from mcgyvr.scan import Disk, Gpu, Machine, Memory, Scan, Vram
from tests.test_recommend import dense_header, invented_model

RIG = "rig-g.invalid"
GB = 1_000_000_000
#: Invented dense coders: a near-copy of the smallest, then doublings.
SIZES = {
    "tiny": 2 * GB,
    "tiny-twin": 2.4 * GB,
    "small": 4 * GB,
    "mid": 8 * GB,
    "big": 16 * GB,
}


def _library() -> planner.Library:
    return planner.Library(
        models=tuple(
            invented_model(
                f"invented-org/coder-{name}",
                dense_header(f"coder-{name}-Q4_K_M.gguf", int(size), context=32768),
            )
            for name, size in SIZES.items()
        )
    )


def _scan(free_mib: int) -> Scan:
    return Scan(
        machine=Machine(id="machine-g", host=RIG, kernel="0.0.0-example"),
        gpus=(
            Gpu(
                index=0,
                name="Example Card W",
                vram=Vram(
                    total_mib=free_mib + 512,
                    used_mib=512,
                    free_mib=free_mib,
                    reserved_mib=0,
                ),
            ),
        ),
        memory=Memory(total_gb=68.0, available_gb=64.0),
        disk=Disk(path=Path("/weights"), free_gb=500.0),
    )


def _ladder(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    free_mib: int,
    *extra: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    monkeypatch.setattr(recommend, "_scan_host", lambda host: _scan(free_mib))
    monkeypatch.setattr(recommend, "load_models", _library)
    code = cli.main(
        ["recommend", "--use-case", "coding", "--users", "1", "--host", RIG, *extra]
    )
    out = capsys.readouterr()
    assert code == 0, out.err
    plan: dict[str, Any] = json.loads(out.out)
    by_name = {u["name"]: u for u in plan["rigs"][RIG]["units"]}
    return plan, [by_name[name] for name in plan["ladder"]]


def _names(rungs: list[dict[str, Any]]) -> list[str]:
    return [rung["model"]["id"].removeprefix("invented-org/coder-") for rung in rungs]


def test_the_ladder_takes_every_clear_step_the_budget_allows(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan, rungs = _ladder(monkeypatch, capsys, 80000)

    assert _names(rungs) == ["tiny", "small", "mid", "big"]
    assert all(rung["role"] == "always-on" for rung in rungs)
    climb = sum(rung["model"]["size_bytes"] for rung in rungs)
    assert climb <= planner.CLIMB_BUDGET * rungs[-1]["model"]["size_bytes"]
    assert plan["manager"]["enable"] is False


def test_a_tighter_budget_leaves_out_the_middle_rung_that_pushes_past_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _plan, rungs = _ladder(monkeypatch, capsys, 80000, "--climb-budget", "1.5")
    assert _names(rungs) == ["tiny", "small", "big"]


def test_a_larger_clear_step_leaves_out_the_near_copies(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _plan, rungs = _ladder(monkeypatch, capsys, 80000, "--clear-step", "3")
    assert _names(rungs) == ["tiny", "big"]


def test_a_top_rung_that_fits_only_alone_sleeps_and_swaps(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan, rungs = _ladder(monkeypatch, capsys, 19000)

    top = rungs[-1]
    assert _names(rungs)[-1] == "big"
    assert top["role"] == "sleeps-until-needed"
    awake = [rung["name"] for rung in rungs[:-1]]
    assert awake and top["swaps_with"] == sorted(awake)
    assert plan["manager"]["enable"] is True
    assert plan["sample"]["swap_round_trip"] is True


def test_throughput_plans_no_rung_that_sleeps(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan, rungs = _ladder(monkeypatch, capsys, 19000, "--priority", "throughput")

    assert all(rung["role"] == "always-on" for rung in rungs)
    assert _names(rungs) == ["tiny", "small", "mid"]
    assert plan["manager"]["enable"] is False
