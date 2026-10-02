"""A fleet's layout holds a spanning unit whole, or it is neither locked nor promoted.

A unit that spans rigs answers at its head only while its workers listen. So a
fleet that places it must hold a room slot for it on EVERY rig it spans, in the
same state (awake or asleep) on all of them, and on no rig it does not span. A
layout that does not describes a unit that cannot serve, and it is refused,
naming the unit, the fleet and the rig, before a lock is written and before a
fleet is promoted. A unit the layout does not place is not judged. A rig's
combination is still that rig's slots alone: a spanning unit changes what a
layout must hold, not how a combination is named.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.fleet import lock, promote
from mcgyvr.fleet.layout import combination_id
from mcgyvr.fleet.spans import SpanError, check_spans
from tests import span_fleet as sf

#: Layouts that split ``big_model``, and what each refusal names.
SPLIT: dict[str, tuple[dict[str, Any], str]] = {
    "on one rig of two": (
        {sf.A: [[sf.BIG, "awake"]]},
        f"{sf.BIG} spans {sf.A}, {sf.B} but holds no room slot on {sf.B}",
    ),
    "awake on one rig and asleep on the other": (
        {sf.A: [[sf.BIG, "awake"]], sf.B: [[sf.BIG, "asleep"]]},
        f"{sf.BIG} is in two states",
    ),
    "with a slot on a rig it does not span": (
        {
            sf.A: [[sf.BIG, "awake"]],
            sf.B: [[sf.BIG, "awake"]],
            "box-c.example": [[sf.BIG, "awake"]],
        },
        "holds a room slot on box-c.example, which it does not span",
    ),
}


def _fleet_with(layout: dict[str, Any]) -> dict[str, Any]:
    fleet = sf.fleet()
    fleet["rigs"]["box-c.example"] = {"rig_id": "rig-" + "c" * 64}
    fleet["fleets"] = {"split": {"layout": layout, "next": []}}
    return fleet


@pytest.mark.parametrize("label", sorted(SPLIT))
def test_check_spans_refuses_a_split_by_unit_fleet_and_rig(label: str) -> None:
    layout, said = SPLIT[label]
    with pytest.raises(SpanError) as refused:
        check_spans(sf.fleet(), layout, name="split")
    text = str(refused.value)
    assert text.startswith("split: ") and said in text, text


def test_a_layout_that_holds_the_unit_whole_is_accepted() -> None:
    fleet = sf.fleet()
    for block in fleet["fleets"].values():
        check_spans(fleet, block["layout"], name="any")
    # A layout that does not place a spanning unit is not judged.
    check_spans(fleet, {sf.A: [[sf.SMALL, "awake"]]})


def test_a_unit_of_one_card_is_held_to_its_rig() -> None:
    fleet = sf.with_small_on_a_card(sf.fleet())
    layout = {sf.A: [[sf.SMALL, "awake"]], sf.B: [[sf.SMALL, "awake"]]}
    with pytest.raises(SpanError, match=f"{sf.SMALL} holds a room slot on {sf.B}"):
        check_spans(fleet, layout, name="pinned")


@pytest.mark.parametrize("label", sorted(SPLIT))
def test_the_lock_refuses_a_split_and_writes_nothing(
    label: str, tmp_path: Path
) -> None:
    layout, said = SPLIT[label]
    fleet = _fleet_with(layout)
    with pytest.raises(lock.LockRefusedError) as refused:
        lock.write(tmp_path, fleet, sf.evidence(), tolerances=sf.TOLERANCES)
    assert "split" in str(refused.value) and said in str(refused.value), refused.value
    assert not any(tmp_path.iterdir())


def test_a_spanning_units_combinations_are_named_per_rig_as_before(
    tmp_path: Path,
) -> None:
    """The lock files one combination per rig, each named from that rig's slots."""
    fleet = sf.fleet()
    lock.write(tmp_path, fleet, sf.evidence(fleet), tolerances=sf.TOLERANCES)
    ids = {sf.BIG: sf.BIG_ID, sf.SMALL: sf.SMALL_ID}
    named = {
        sf.RIG_A: combination_id(
            sf.RIG_A, [(ids[sf.BIG], "awake"), (ids[sf.SMALL], "awake")]
        ),
        sf.RIG_B: combination_id(sf.RIG_B, [(ids[sf.BIG], "awake")]),
    }
    for rig_id, expected in named.items():
        where = tmp_path / promote.LOCK_DIR / "rigs" / rig_id
        assert (where / f"{expected}.json").is_file(), sorted(
            p.name for p in where.iterdir()
        )


# --- promote ---------------------------------------------------------------


def _setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, layout: Any
) -> tuple[Path, Path]:
    """A dev root holding the lock of the whole fleet, and a setup directory
    whose ``fleet.yaml`` spells the ``whole`` fleet's layout as ``layout``."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("MCGYVR_HOME", raising=False)
    fleet = sf.fleet()
    dev = tmp_path / "dev"
    lock.write(dev, fleet, sf.evidence(fleet), tolerances=sf.TOLERANCES)
    edited = copy.deepcopy(fleet)
    edited["fleets"]["whole"]["layout"] = layout
    setup = tmp_path / "setup"
    setup.mkdir()
    (setup / "fleet.yaml").write_text(yaml.safe_dump(edited), encoding="utf-8")
    (setup / "policy.yaml").write_text(
        yaml.safe_dump({"ladder": [sf.BIG, sf.SMALL]}), encoding="utf-8"
    )
    return dev, setup


@pytest.mark.parametrize(
    "label", ["on one rig of two", "awake on one rig and asleep on the other"]
)
def test_promote_refuses_a_fleet_that_splits_a_spanning_unit(
    label: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout, said = SPLIT[label]
    dev, setup = _setup(tmp_path, monkeypatch, layout)
    with pytest.raises(promote.PromoteRefusedError) as refused:
        promote.promote(dev, setup, "whole")
    text = str(refused.value)
    assert "whole" in text and said in text, text
    assert not (tmp_path / "home" / ".mcgyvr" / "fleets").exists(), (
        "a refused promotion writes nothing"
    )


def test_promote_carries_a_whole_spanning_fleet_with_both_its_rigs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    whole = sf.fleet()["fleets"]["whole"]["layout"]
    dev, setup = _setup(tmp_path, monkeypatch, whole)
    folder = promote.promote(dev, setup, "whole")
    carried = yaml.safe_load((folder / "fleet.yaml").read_text(encoding="utf-8"))
    assert set(carried["rigs"]) == {sf.A, sf.B}
    assert set(carried["units"]) == {sf.BIG, sf.SMALL}
    assert json.loads((folder / promote.LOCK_DIR / "whole.json").read_text())
