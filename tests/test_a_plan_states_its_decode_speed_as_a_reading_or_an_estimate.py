"""A plan states its decode speed as a reading or an estimate, or says why not.

A plan's placement states how fast its model decodes on the card it is placed
on: the speed the live fleet measured for that model at that host when there is
one, else an estimate from the bandwidth of the card's class, labelled as one,
else no value and the reason. Each card in the plan states its class bandwidth
the same way. The machine, the table of classes, the catalog and the fleet are
invented.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr import estimate, recommend
from mcgyvr.scan import Scan
from tests import hwclasses, machine_shapes, sample_fleet

HOST = "box-1.example"
MODEL = "invented-org/invented-dense"
SIZE = 4_000_000_000
CATALOG: dict[str, Any] = {
    "models": [
        {
            "model_id": MODEL,
            "quant": "Q4_K_M",
            "size_bytes": SIZE,
            "token_bytes": SIZE,
            "context_length": 32768,
            "kv_bytes_per_token": 1000,
            "recurrent_bytes_per_slot": 0,
            "engines": ["llama.cpp"],
        }
    ],
}


@pytest.fixture(autouse=True)
def _invented(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    table = hwclasses.table(tmp_path)
    monkeypatch.setattr(estimate, "_shipped", lambda: table)
    monkeypatch.setattr(recommend, "load_catalog", lambda *a, **k: CATALOG)


def unified() -> Scan:
    return machine_shapes.host_scan(machine_shapes.host_shape("unified-laptop"))


def placed(scan: Scan, readings: dict[tuple[str, str], float]) -> dict[str, Any]:
    plan = recommend.plan(
        profile="chat",
        users=1,
        hosts=(HOST,),
        premeasured={HOST: scan},
        readings=readings,
    )
    return plan


def test_before_any_reading_the_placement_states_the_class_estimate() -> None:
    plan = placed(unified(), {})
    decode = plan["placement"]["decode_tok_s"]
    assert decode["figure"] == "estimate"
    # A scan does not carry the GPU's cores, so of the chip's two bandwidths the
    # lower answers.
    bandwidth = next(one for one in hwclasses.ROWS if one["id"] == "chip-u1-8c")
    expected = (
        estimate.DECODE_EFFICIENCY["4bit"] * bandwidth["bandwidth_gbps"] / (SIZE / 1e9)
    )
    assert decode["value"] == pytest.approx(expected, abs=0.05)
    (gpu,) = plan["rigs"][0]["measured"]["gpus"]
    assert gpu["kind"] == "unified" and gpu["vram_figure"] == "estimate"
    assert gpu["bandwidth_gbps"]["value"] == bandwidth["bandwidth_gbps"]
    assert gpu["bandwidth_gbps"]["figure"] == "estimate"


def test_the_fleets_reading_replaces_the_estimate() -> None:
    decode = placed(unified(), {(HOST, MODEL): 17.5})["placement"]["decode_tok_s"]
    assert (decode["value"], decode["figure"]) == (17.5, "reading")


def test_a_card_of_no_class_states_no_value_and_why() -> None:
    scan = machine_shapes.host_scan(machine_shapes.host_shape("windows-one-card"))
    plan = placed(scan, {})
    decode = plan["placement"]["decode_tok_s"]
    assert decode["value"] is None and decode["figure"] is None
    assert "no estimate" in decode["why"]


def test_the_live_fleets_lock_gives_the_slowest_measured_decode_by_host_and_model(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "fleet"
    rigs = folder / "lock" / "rigs" / "rig-example"
    rigs.mkdir(parents=True)
    (folder / "fleet.yaml").write_text(
        yaml.safe_dump(sample_fleet.fleet_doc()), encoding="utf-8"
    )
    unit = sample_fleet.UNIT
    for name, warm in (("a", 40.0), ("b", 30.0)):
        (rigs / f"{name}.json").write_text(
            f'{{"approved": {{"{unit}": {{"warm_decode_tok_s": {warm}}},'
            f' "not-a-unit": {{"warm_decode_tok_s": 99.0}}}}}}',
            encoding="utf-8",
        )
    model = sample_fleet.unit()["model"]
    assert estimate.decode_readings(folder) == {(sample_fleet.RIG, model): 30.0}


def test_no_live_fleet_gives_no_readings(tmp_path: Path) -> None:
    assert estimate.decode_readings(tmp_path / "nowhere") == {}
