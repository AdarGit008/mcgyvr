"""A coding rig puts work on every card.

Owner, Round 9: "idle cards: FILL them. A coding rig's spare cards get another
awake rung or another copy of a rung, so all cards work." Which one is decided
by the ladder's own rules (owner, Round 7): another rung only when it is a
clear quality step up and a climb through every rung stays within the climb
budget; otherwise a copy of the rung that does the most work there, filled
with slots.

A copy is what the router already serves a rung's peers as: a unit of its
own, serving the same model on its own card and port, listed on the ladder
beside the rung it copies, so that under ``fanout: idle`` a batch starts on
whichever of them has a free slot (:mod:`mcgyvr.route`). A copy is not a step
up: the climb budget and the clear step are over the ladder's models.

Promises, on invented machines:

* From the shipped knowledge, on one or several machines with one or several
  cards of 6, 12 or 24 GB: every card a coder fits on wholly holds an
  always-on rung or copy of its machine's ladder; the copies of one model are
  listed together; each model up a machine's ladder is a clear step above the
  one below, and where a middle rung was added, a climb through its models
  stays within the budget.
* Over invented coders on three cards: a model that is a clear step and keeps
  the climb within the budget is another rung on the spare card; with a larger
  clear step, or a tighter budget, that leaves it out, the spare card holds a
  copy of the fast rung, with more than one slot, and the plan fans out.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import cli, planner, recommend
from mcgyvr.scan import Disk, Gpu, Machine, Memory, Scan, Vram
from tests.test_recommend import dense_header, invented_model

SHAPES: dict[str, dict[str, tuple[int, ...]]] = {
    "1x12": {"rig-a.invalid": (11800,)},
    "2x12+6": {"rig-b.invalid": (11800, 11800, 5800)},
    "1x24": {"rig-c.invalid": (24000,)},
    "2x12|6": {"rig-d.invalid": (11800, 11800), "rig-e.invalid": (5800,)},
}

GB = 1_000_000_000
#: Invented dense coders: each a clear step (1.5x) above the one below.
SIZES = {"tiny": 2 * GB, "mid": 5 * GB, "big": 9 * GB}


def _scan(host: str, free_mib: tuple[int, ...]) -> Scan:
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
        memory=Memory(total_gb=68.0, available_gb=64.0),
        disk=Disk(path=Path("/weights"), free_gb=500.0),
    )


def _plan(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    rigs: dict[str, tuple[int, ...]],
    *extra: str,
) -> dict[str, Any]:
    scans = {host: _scan(host, free) for host, free in rigs.items()}
    monkeypatch.setattr(recommend, "_scan_host", lambda host: scans[host])
    argv = ["recommend", "--use-case", "coding", "--users", "1", *extra]
    for host in rigs:
        argv += ["--host", host]
    code = cli.main(argv)
    out = capsys.readouterr()
    assert code == 0, out.err
    plan: dict[str, Any] = json.loads(out.out)
    return plan


def _ladder_of(plan: dict[str, Any], rig: str) -> list[dict[str, Any]]:
    names = {unit["name"]: unit for unit in plan["rigs"][rig]["units"]}
    return [names[name] for name in plan["ladder"] if name in names]


def _distinct(rungs: list[dict[str, Any]]) -> list[str]:
    """The ladder's models in order, each once: what a climb steps through."""
    return list(dict.fromkeys(rung["model"]["id"] for rung in rungs))


def _working_cards(rungs: list[dict[str, Any]]) -> set[int]:
    return {
        card for rung in rungs if rung["role"] == "always-on" for card in rung["cards"]
    }


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_card_of_every_coding_rig_works(
    shape: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rigs = SHAPES[shape]
    plan = _plan(monkeypatch, capsys, rigs, "--offline")
    models = {model.model_id: model for model in planner.library().models}

    for rig, free in rigs.items():
        rungs = _ladder_of(plan, rig)
        assert _working_cards(rungs) == set(range(len(free))), (rig, rungs)
        ids = [rung["model"]["id"] for rung in rungs]
        for model_id in set(ids):
            at = [i for i, one in enumerate(ids) if one == model_id]
            assert at == list(range(at[0], at[0] + len(at))), ids
        steps = [models[one] for one in _distinct(rungs)]
        for lower, upper in itertools.pairwise(steps):
            assert planner.clear_step(
                "coding", lower, upper, step=planner.CLEAR_STEP
            ), (lower.model_id, upper.model_id)
        if len(steps) > 2:
            climb = sum(planner.token_bytes(model) for model in steps)
            assert climb <= planner.CLIMB_BUDGET * planner.token_bytes(steps[-1])


THREE_CARDS: dict[str, tuple[int, ...]] = {"rig-f.invalid": (11800, 11800, 11800)}


def _invented() -> planner.Library:
    return planner.Library(
        models=tuple(
            invented_model(
                f"invented-org/coder-{name}",
                dense_header(f"coder-{name}-Q4_K_M.gguf", int(size), context=32768),
            )
            for name, size in SIZES.items()
        )
    )


def _short(rungs: list[dict[str, Any]]) -> list[str]:
    return [rung["model"]["id"].removeprefix("invented-org/coder-") for rung in rungs]


def test_a_clear_step_within_the_budget_is_another_rung_on_the_spare_card(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(recommend, "load_models", _invented)
    plan = _plan(monkeypatch, capsys, THREE_CARDS)

    rungs = _ladder_of(plan, "rig-f.invalid")
    assert _short(rungs) == ["tiny", "mid", "big"]
    assert _working_cards(rungs) == {0, 1, 2}


@pytest.mark.parametrize(
    "extra", [("--clear-step", "3"), ("--climb-budget", "1.4")], ids=str
)
def test_with_no_rung_to_add_the_spare_card_copies_the_fast_rung(
    extra: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(recommend, "load_models", _invented)
    plan = _plan(monkeypatch, capsys, THREE_CARDS, *extra)

    rungs = _ladder_of(plan, "rig-f.invalid")
    assert _short(rungs) == ["tiny", "tiny", "big"]
    assert _working_cards(rungs) == {0, 1, 2}
    first, copy, _top = rungs
    assert first["cards"] != copy["cards"]
    assert first["name"] != copy["name"] and first["port"] != copy["port"]
    assert copy["role"] == "always-on"
    assert copy["slots"] > 1
    assert copy["ctx_per_slot"] == first["ctx_per_slot"] == 8192
    assert plan["fanout"] == "idle"
