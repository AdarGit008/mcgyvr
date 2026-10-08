"""A plan stages as the fleet its sample runs on, pinned once the rig is read.

Plan section 8.1 (P7b): the confirmed plan is started and sampled as a staged
setup -- the ``fleet.yaml`` and ``policy.yaml`` the sample (P7a) judges and
the stamp locks. Each unit carries what the plan sized: its role, rig, card,
model, context per slot (``window``) and slots (``width``), and the launch
``mcgyvr emit`` would render for it. Owner, Round 8: a sleeper's swap is two
fleets, F and F-strong, each in the other's ``next``; the sleeper takes the
slot of its first swap partner, and the partners it also stops leave theirs
free (``fleet-identity.md`` ID-4: a freed room is a free slot).

Owner, option A (2026-10-08): the ids are provisional until the rig is read.
``rig-`` is then the id the read's snapshot names, and ``unt-`` the digest of
the unit's engine, image Id, weights sha256, argv, env and the compute
capability of its cards (ID-1, ID-2), and the staged ``fleet.yaml`` is
rewritten with both.

No rig is reached: the plans and the machines are invented.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests import sample_fleet as fx
from tests import staged_plans as sp

IMAGE_ID = "sha256:" + "e" * 64


def _stage(tmp_path: Path, plan: dict[str, Any], scans: Any) -> Any:
    from mcgyvr.fleet import staged

    return staged.stage(plan, scans, tmp_path / "staged", models=sp.library().models)


def _fleet(folder: Path) -> dict[str, Any]:
    doc: dict[str, Any] = yaml.safe_load(
        (folder / "fleet.yaml").read_text(encoding="utf-8")
    )
    return doc


def _snapshot() -> dict[str, str]:
    return {**fx.SNAPSHOT, "hostname": sp.RIG}


def test_each_unit_carries_what_the_plan_sized_and_the_launch_emit_renders(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr import emit, planner

    plan, scans = sp.coding_plan(monkeypatch, capsys)
    done = _stage(tmp_path, plan, scans)

    fleet = _fleet(done.folder)
    planned = sp.units(plan)
    assert set(fleet["units"]) == set(planned)
    built = {
        unit.port: unit for unit in planner.units_of(plan, scans, sp.library().models)
    }
    for name, unit in fleet["units"].items():
        laid = planned[name]
        assert unit["role"] == laid["role"]
        assert unit["rig"] == sp.RIG
        assert unit["width"] == laid["slots"]
        assert unit["window"] == laid["ctx_per_slot"]
        assert unit["engine"] == "llama.cpp"
        assert unit["address"] == f"http://{sp.RIG}:{laid['port']}"
        room = math.ceil(laid["fit"]["vram_gib"] * 1024)
        assert unit["room_mib"] == room
        assert unit["launch"]["shards"] == [
            {"rig": sp.RIG, "gpu": laid["cards"][0], "room_mib": room}
        ]
        assert unit["launch"]["weights_sha256"] == laid["download"]["sha256"]
        rendered = yaml.safe_load(emit.render_compose(built[laid["port"]]))
        (service,) = rendered["services"].values()
        assert unit["model"] == built[laid["port"]].model
        assert unit["launch"]["argv"] == service["command"]
        assert unit["launch"]["env"] == service["environment"]
        assert unit["launch"]["volumes"] == service["volumes"]
        assert unit["image"] == service["image"]
        assert unit["container"] == service["container_name"]


def test_a_sleeper_swaps_in_as_the_strong_fleet_each_fleet_in_the_others_next(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr import config
    from mcgyvr.fleet import staged

    plan, scans = sp.coding_plan(monkeypatch, capsys)
    done = _stage(tmp_path, plan, scans)

    fleet = _fleet(done.folder)
    planned = sp.units(plan)
    (sleeper,) = [n for n, u in planned.items() if u["role"] == "sleeps-until-needed"]
    awake = [n for n in plan["ladder"] if n != sleeper]
    strong = staged.strong_name(plan["fleet"])
    assert done.fleet == plan["fleet"] and done.strong == strong
    assert fleet["fleets"] == {
        plan["fleet"]: {
            "layout": {sp.RIG: [[name, "awake"] for name in awake]},
            "next": [strong],
        },
        strong: {
            "layout": {
                sp.RIG: [[sleeper, "awake"], *([None] * (len(awake) - 1))],
            },
            "next": [plan["fleet"]],
        },
    }
    assert set(planned[sleeper]["swaps_with"]) == set(awake)
    policy = yaml.safe_load((done.folder / "policy.yaml").read_text("utf-8"))
    assert policy["use_case"] == "coding"
    assert policy["ladder"] == plan["ladder"]
    assert policy["users"] == plan["users"]
    config.load(done.folder)


def test_a_chat_plan_stages_one_fleet_with_nowhere_to_switch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan, scans = sp.chat_plan(monkeypatch, capsys)
    done = _stage(tmp_path, plan, scans)

    fleet = _fleet(done.folder)
    ((name, unit),) = fleet["units"].items()
    assert done.strong is None
    assert fleet["fleets"] == {
        plan["fleet"]: {"layout": {sp.RIG: [[name, "awake"]]}, "next": []}
    }
    assert unit["role"] == "always-on"


def test_the_staged_fleets_render_as_one_launch_spec_each(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr import emit

    plan, scans = sp.coding_plan(monkeypatch, capsys)
    done = _stage(tmp_path, plan, scans)
    fleet = _fleet(done.folder)

    written = emit.emit_locked(fleet, tmp_path / "compose", done.folder)

    by_name = {path.name: yaml.safe_load(path.read_text("utf-8")) for path in written}
    strong = by_name[f"compose.{sp.RIG}.{done.strong}.yml"]
    (sleeper,) = [
        unit["container"]
        for unit in fleet["units"].values()
        if unit["role"] == "sleeps-until-needed"
    ]
    assert [s["container_name"] for s in strong["services"].values()] == [sleeper]
    fast = by_name[f"compose.{sp.RIG}.{done.fleet}.yml"]
    assert sleeper not in [s["container_name"] for s in fast["services"].values()]


def test_the_ids_are_provisional_until_the_rig_is_read_and_then_pinned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr import config
    from mcgyvr.fleet import ids, staged

    plan, scans = sp.coding_plan(monkeypatch, capsys)
    done = _stage(tmp_path, plan, scans)
    before = _fleet(done.folder)
    assert staged.provisional(before)
    images = {unit["image"]: IMAGE_ID for unit in before["units"].values()}
    snapshot = _snapshot()

    staged.pin(done.folder, snapshots={sp.RIG: snapshot}, images=images)

    after = _fleet(done.folder)
    assert not staged.provisional(after)
    assert after["rigs"] == {sp.RIG: {"rig_id": ids.rig_id(snapshot)}}
    assert after["fleets"] == before["fleets"]
    for name, unit in after["units"].items():
        launch = unit["launch"]
        assert unit["unit_id"] == ids.digest(
            "unt-",
            {
                "engine": "llama.cpp",
                "image": IMAGE_ID,
                "weights_sha256": launch["weights_sha256"],
                "argv": launch["argv"],
                "env": launch["env"],
                "gpu_cc": [snapshot["gpu_cc"]],
            },
        ), name
        assert unit["unit_id"] != before["units"][name]["unit_id"]
    config.load(done.folder)


def test_another_image_is_another_unit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.fleet import staged

    plan, scans = sp.chat_plan(monkeypatch, capsys)
    first = _stage(tmp_path / "a", plan, scans)
    second = _stage(tmp_path / "b", plan, scans)
    (image,) = {u["image"] for u in _fleet(first.folder)["units"].values()}

    staged.pin(first.folder, snapshots={sp.RIG: _snapshot()}, images={image: IMAGE_ID})
    staged.pin(
        second.folder,
        snapshots={sp.RIG: _snapshot()},
        images={image: "sha256:" + "f" * 64},
    )

    (one,) = _fleet(first.folder)["units"].values()
    (two,) = _fleet(second.folder)["units"].values()
    assert one["unit_id"] != two["unit_id"]


@pytest.mark.parametrize("missing", ["image", "snapshot", "cc"])
def test_a_pin_with_a_fact_unread_is_refused_by_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    missing: str,
) -> None:
    from mcgyvr.fleet import staged

    plan, scans = sp.chat_plan(monkeypatch, capsys)
    done = _stage(tmp_path, plan, scans)
    before = (done.folder / "fleet.yaml").read_text("utf-8")
    (image,) = {u["image"] for u in _fleet(done.folder)["units"].values()}
    snapshot = _snapshot()
    images = {image: IMAGE_ID}
    snapshots = {sp.RIG: snapshot}
    if missing == "image":
        images = {}
    elif missing == "snapshot":
        snapshots = {}
    else:
        snapshot["gpu_cc"] = ""

    with pytest.raises(staged.StageError) as refused:
        staged.pin(done.folder, snapshots=snapshots, images=images)

    said = str(refused.value)
    assert {"image": image, "snapshot": sp.RIG, "cc": "gpu_cc"}[missing] in said, said
    assert (done.folder / "fleet.yaml").read_text("utf-8") == before, (
        "a refused pin leaves the staged fleet as it was"
    )
