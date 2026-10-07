"""A chat (or agent) plan is one strong unit, at the most context that fits.

Owner, 2026-10-07: "chat and agent: one strong unit with extended context";
Round 3: "chat + agent = the MAXIMUM context that fits". Plan section 3: the
unit is on one card, split across cards, or an MoE with its experts in RAM;
its slots are the users; its context per slot is the most that fits, capped
at the model's own context. Section 5: the KV cache is f16, and q8_0 only
when f16 misses the context the use case needs.

Promises, over invented rigs and the shipped knowledge:

* One machine of one card gets one unit, ``always-on``, with one slot per
  user. (Several cards or machines: one unit spans them all, pinned by
  ``tests/test_a_chat_plan_spans_every_card_with_the_biggest_model_that_fits.py``.)
* Its context per slot is the most the serving sizer admits at that many
  slots: one step more does not fit, unless the model's own context is
  reached first. Its KV cache is f16, unless f16 does not fit the least
  context a strong unit is given; then the unit says why.
* The unit is the strongest model serving the use case that fits at the
  least context a strong unit is given: the largest, when no board scores
  them and none needs RAM for its experts.
* A model too large for any one card is split across the rig's cards when
  that fits.
* An MoE spills its experts to RAM: with no RAM to hold them it is not
  planned, and the plan says why.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import cli, planner, serving
from mcgyvr.knowledge import geometry as kg
from mcgyvr.scan import Disk, Gpu, Machine, Memory, Scan, Vram

RIG = "rig-c.invalid"


def _scan(free_mib: tuple[int, ...], ram_gb: float) -> Scan:
    return Scan(
        machine=Machine(id="machine-c", host=RIG, kernel="0.0.0-example"),
        gpus=tuple(
            Gpu(
                index=index,
                name="Example Card Z",
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
    scan: Scan,
    *,
    use_case: str = "chat",
    users: int = 1,
) -> dict[str, Any]:
    monkeypatch.setattr(planner_scan_seam(), "_scan_host", lambda host: scan)
    code = cli.main(
        [
            "recommend",
            "--use-case",
            use_case,
            "--users",
            str(users),
            "--host",
            RIG,
            "--offline",
        ]
    )
    out = capsys.readouterr()
    assert code == 0, out.err
    plan: dict[str, Any] = json.loads(out.out)
    return plan


def planner_scan_seam() -> Any:
    from mcgyvr import recommend

    return recommend


def _spec(unit: Mapping[str, Any]) -> serving.ModelSpec:
    rows = kg.load().rows
    model = unit["model"]
    row = rows[(model["repo"], model["revision"], model["file"])].row
    return serving.ModelSpec(
        name=Path(model["file"]).stem,
        vram_gb=0.0,
        ram_gb=0.0,
        disk_gb=0.0,
        geometry=row,
        kv_cache_dtype_k=unit["kv_cache"]["k"],
        kv_cache_dtype_v=unit["kv_cache"]["v"],
        speculative=unit["speculative"],
    )


@pytest.mark.parametrize("use_case", ["chat", "agent"])
@pytest.mark.parametrize("users", [1, 3])
def test_one_unit_per_rig_at_one_slot_per_user_and_the_most_context_that_fits(
    use_case: str,
    users: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scan = _scan((11800,), ram_gb=0.0)
    plan = _plan(monkeypatch, capsys, scan, use_case=use_case, users=users)

    ((rig, laid),) = plan["rigs"].items()
    assert rig == RIG
    (unit,) = laid["units"]
    assert unit["role"] == "always-on"
    assert unit["slots"] == users
    assert plan["ladder"] == [unit["name"]]
    ctx = unit["ctx_per_slot"]
    cap = unit["model"]["context_length"]
    spec = _spec(unit)
    assert serving.fit(
        scan, spec, engine="llama.cpp", width=users, ctx_per_slot=ctx
    ).fits
    if ctx < cap:
        more = min(cap, ctx + planner.CONTEXT_STEP)
        assert not serving.fit(
            scan, spec, engine="llama.cpp", width=users, ctx_per_slot=more
        ).fits
    if unit["kv_cache"]["k"] != "f16":
        assert unit["notes"], "a cache that is not f16 says why"
        f16 = dataclasses.replace(spec, kv_cache_dtype_k="f16", kv_cache_dtype_v="f16")
        least = min(planner.STRONG_MIN_CTX, cap)
        assert not serving.fit(
            scan, f16, engine="llama.cpp", width=users, ctx_per_slot=least
        ).fits


def test_with_no_board_the_strongest_is_the_largest_that_fits(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scan = _scan((11800,), ram_gb=0.0)
    plan = _plan(monkeypatch, capsys, scan)

    (unit,) = plan["rigs"][RIG]["units"]
    fitting = [
        model
        for model in planner.library().models
        if planner.serves(model, "chat")
        and any(
            serving.fit(
                scan,
                planner.spec_of(model, kv=kv),
                engine="llama.cpp",
                width=1,
                ctx_per_slot=min(planner.STRONG_MIN_CTX, model.context_length),
            ).fits
            for kv in planner.KV_TYPES
        )
    ]
    assert fitting
    largest = max(fitting, key=lambda model: model.size_bytes)
    assert unit["model"]["id"] == largest.model_id


def test_a_model_too_large_for_one_card_is_split_across_the_rigs_cards(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    library = planner.library()
    dense = [
        m
        for m in library.models
        if not m.geometry.get("placeable_blocks") and planner.serves(m, "chat")
    ]
    largest = max(dense, key=lambda model: model.size_bytes)
    half = (largest.size_bytes >> 20) * 4 // 5
    monkeypatch.setattr(
        planner_scan_seam(),
        "load_models",
        lambda: dataclasses.replace(library, models=(largest,)),
    )
    scan = _scan((half, half), ram_gb=0.0)

    plan = _plan(monkeypatch, capsys, scan)

    (unit,) = plan["rigs"][RIG]["units"]
    assert unit["model"]["id"] == largest.model_id
    assert unit["cards"] == [0, 1]


def test_an_moe_with_no_ram_for_its_experts_is_not_planned_and_says_why(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    library = planner.library()
    moe = [
        m
        for m in library.models
        if m.geometry.get("placeable_blocks") and planner.serves(m, "chat")
    ]
    assert moe, "the shipped knowledge holds an MoE"
    scan = _scan((8192,), ram_gb=0.0)
    monkeypatch.setattr(
        planner_scan_seam(),
        "load_models",
        lambda: dataclasses.replace(library, models=tuple(moe)),
    )
    monkeypatch.setattr(planner_scan_seam(), "_scan_host", lambda host: scan)

    code = cli.main(
        ["recommend", "--use-case", "chat", "--users", "1", "--host", RIG, "--offline"]
    )
    out = capsys.readouterr()

    assert code == 1
    assert "RAM" in out.err
