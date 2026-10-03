"""A locked unit reserves the cards its shards name, and nothing else.

Promise: a locked unit is rendered from the launch it states, and so are the
cards it holds. A unit that names its cards in ``launch.shards`` reserves
exactly those of the rig being rendered: both cards of a unit split across one
machine's two cards, card 1 for a unit pinned there. A unit that names none
keeps the one card it always reserved, card 0. A locked launch states one
argv, its head's, so a unit that spans rigs is refused by name rather than
rendered as a second head on its worker's rig.

Rigs and units are invented.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.emit import LockedLaunchError, emit_locked

A = "box-a.example"
B = "box-b.example"


def unit(name: str, port: int, *, rig: str = A, shards: Any = None) -> dict[str, Any]:
    launch: dict[str, Any] = {
        "argv": ["--model", f"/srv/weights/{name}.gguf", "--port", str(port)],
        "env": {},
        "volumes": ["/srv/weights:/srv/weights:ro"],
    }
    if shards is not None:
        launch["shards"] = shards
    return {
        "unit_id": f"unit-{name}",
        "engine": "llama.cpp",
        "image": "example.invalid/llama-server:pinned",
        "container": f"mcgyvr-{name}",
        "rig": rig,
        "address": f"http://{rig}:{port}",
        "launch": launch,
    }


def fleet(units: dict[str, dict[str, Any]], layout: dict[str, Any]) -> dict[str, Any]:
    return {
        "rigs": {A: {}, B: {}},
        "units": units,
        "fleets": {"one": {"layout": layout}},
    }


def reserved(out: Path, host: str, service: str) -> list[str]:
    doc = yaml.safe_load((out / f"compose.{host}.one.yml").read_text("utf-8"))
    deploy = doc["services"][service]["deploy"]
    devices = deploy["resources"]["reservations"]["devices"]
    return list(devices[0]["device_ids"])


def test_a_unit_split_over_two_cards_of_one_rig_reserves_both(tmp_path: Path) -> None:
    shards = [{"rig": A, "gpu": 0}, {"rig": A, "gpu": 1}]
    doc = fleet({"big": unit("big", 8080, shards=shards)}, {A: [["big", "awake"]]})
    emit_locked(doc, tmp_path)
    assert reserved(tmp_path, A, "big") == ["0", "1"]


def test_a_unit_pinned_to_one_card_reserves_that_card(tmp_path: Path) -> None:
    doc = fleet(
        {
            "small": unit("small", 8080),
            "pinned": unit("pinned", 8081, shards=[{"rig": A, "gpu": 1}]),
        },
        {A: [["small", "awake"], ["pinned", "awake"]]},
    )
    emit_locked(doc, tmp_path)
    assert reserved(tmp_path, A, "pinned") == ["1"]
    assert reserved(tmp_path, A, "small") == ["0"]


def test_a_unit_that_spans_rigs_is_refused_by_name_before_anything_is_written(
    tmp_path: Path,
) -> None:
    shards = [{"rig": A, "gpu": 0}, {"rig": B, "gpu": 0}]
    doc = fleet(
        {"wide": unit("wide", 8080, shards=shards)},
        {A: [["wide", "awake"]], B: [["wide", "awake"]]},
    )
    out = tmp_path / "compose"
    with pytest.raises(LockedLaunchError, match=r"wide.*box-b\.example"):
        emit_locked(doc, out)
    assert not out.exists() or not any(out.iterdir())
