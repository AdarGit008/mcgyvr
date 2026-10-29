"""A device's class is found by its name and memory, or not at all.

A device is looked up by its name without vendor words, matched whole, so a
neighbouring model or a laptop part never takes another's bandwidth. A card
that comes with two memory sizes is told apart by its memory and gets no class
when that is unread; a chip with two bandwidths is told apart by its GPU cores
or the machine's memory, and the lower bandwidth answers when they are unread.
A device no row names gets no estimate and says so. The table here is
invented; the shipped table is held to its shape: every row sourced, every
row saying whether its source was read cleanly.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import estimate
from tests import hwclasses, machine_shapes
from tests._paths import REPO

GIB = 1 << 30


@pytest.fixture
def table(tmp_path: Path) -> tuple[estimate.HardwareClass, ...]:
    return hwclasses.table(tmp_path)


def _id(found: estimate.HardwareClass | estimate.NoEstimate) -> str:
    assert isinstance(found, estimate.HardwareClass), found
    return found.id


@pytest.mark.parametrize(
    ("name", "vram_mib", "expected"),
    [
        (f"NVIDIA GeForce {hwclasses.CARD}", 10240, "card-70-10gb"),
        (f"NVIDIA GeForce {hwclasses.CARD}", 10234, "card-70-10gb"),
        (f"NVIDIA {hwclasses.CARD}", 6144, "card-70-6gb"),
        (hwclasses.CARD, 6138, "card-70-6gb"),
    ],
)
def test_a_card_is_its_name_then_its_memory(
    table: tuple[estimate.HardwareClass, ...], name: str, vram_mib: int, expected: str
) -> None:
    assert _id(estimate.match(name, vram_mib=vram_mib, classes=table)) == expected


@pytest.mark.parametrize(
    ("name", "vram_mib"),
    [
        (f"NVIDIA GeForce {hwclasses.CARD}", 16384),
        (f"NVIDIA GeForce {hwclasses.CARD}", None),
        (f"NVIDIA GeForce {hwclasses.CARD} Ti", 10240),
        (f"NVIDIA GeForce {hwclasses.CARD} Laptop GPU", 10240),
        ("Example Card 9000", 10240),
    ],
)
def test_a_card_of_no_class_or_of_an_unknown_variant_gets_none(
    table: tuple[estimate.HardwareClass, ...], name: str, vram_mib: int | None
) -> None:
    found = estimate.match(name, vram_mib=vram_mib, classes=table)
    assert isinstance(found, estimate.NoEstimate)
    assert "estimate" in found.why or "variant" in found.why


@pytest.mark.parametrize(
    ("name", "cores", "memory_gb", "expected"),
    [
        (f"{hwclasses.CHIP} GPU", 10, 32, "chip-u1-10c"),
        (f"Apple {hwclasses.CHIP}", 8, 16, "chip-u1-8c"),
        (f"{hwclasses.CHIP} GPU", None, 32, "chip-u1-8c"),
        (f"{hwclasses.CHIP_BY_MEMORY} GPU", None, 16, "chip-u2-small"),
        (f"{hwclasses.CHIP_BY_MEMORY} GPU", 12, 32, "chip-u2-large"),
        (f"{hwclasses.CHIP_BY_MEMORY} GPU", None, None, "chip-u2-small"),
    ],
)
def test_a_chip_is_its_name_then_its_cores_or_memory_else_the_slower(
    table: tuple[estimate.HardwareClass, ...],
    name: str,
    cores: int | None,
    memory_gb: int | None,
    expected: str,
) -> None:
    memory = None if memory_gb is None else memory_gb * 1024
    found = estimate.match(name, gpu_cores=cores, memory_mib=memory, classes=table)
    assert _id(found) == expected


def test_an_estimate_from_the_slower_of_two_variants_says_so(
    table: tuple[estimate.HardwareClass, ...],
) -> None:
    got = estimate.device_decode(
        f"{hwclasses.CHIP} GPU", model_bytes=4 * GIB, quant="Q4_0", classes=table
    )
    assert isinstance(got, estimate.Figure)
    assert "chip-u1-8c" in got.basis and "slower of 2 variants" in got.basis


def test_an_unknown_chip_gets_no_estimate_and_a_note(
    table: tuple[estimate.HardwareClass, ...],
) -> None:
    got = estimate.device_decode(
        "Example Chip U9 GPU", model_bytes=4 * GIB, quant="Q4_0", classes=table
    )
    assert isinstance(got, estimate.NoEstimate)
    assert "Example Chip U9 GPU" in got.why and "no estimate" in got.why


def test_an_invented_unified_machine_decodes_at_its_class_bandwidth(
    table: tuple[estimate.HardwareClass, ...],
) -> None:
    machine = machine_shapes.host_shape("unified-laptop")
    gpu = machine_shapes.host_scan(machine).gpus[0]
    model = int(3.56 * GIB)
    got = estimate.device_decode(
        gpu.name,
        model_bytes=model,
        quant="Q4_K_M",
        gpu_cores=machine.gpu_cores,
        memory_mib=machine.memory_mib,
        classes=table,
    )
    assert isinstance(got, estimate.Figure) and got.figure == "estimate"
    row = next(one for one in table if one.id == "chip-u1-10c")
    assert got.value == pytest.approx(
        estimate.DECODE_EFFICIENCY["4bit"] * row.bandwidth_gbps / (model / 1e9)
    )
    assert "chip-u1-10c" in got.basis and "variants" not in got.basis


def test_the_machines_reading_replaces_the_class_estimate(
    table: tuple[estimate.HardwareClass, ...],
) -> None:
    got = estimate.device_decode(
        f"{hwclasses.CHIP} GPU",
        model_bytes=4 * GIB,
        quant="Q4_0",
        reading=21.0,
        classes=table,
    )
    assert isinstance(got, estimate.Figure)
    assert (got.value, got.figure) == (21.0, "reading")


def test_an_unverified_row_is_used_and_flagged(
    table: tuple[estimate.HardwareClass, ...],
) -> None:
    got = estimate.device_decode(
        f"{hwclasses.CHIP_BY_MEMORY} GPU",
        model_bytes=4 * GIB,
        quant="Q8_0",
        memory_mib=24 * 1024,
        classes=table,
    )
    assert isinstance(got, estimate.Figure) and not got.verified


@pytest.mark.parametrize(
    "broken",
    [
        {"schema": 99},
        {"extra": 1},
        {"classes": []},
        {"classes": [{**hwclasses.ROWS[0], "score": 1}]},
        {"classes": [{**hwclasses.ROWS[0], "bandwidth_gbps": 0}]},
        {"classes": [{**hwclasses.ROWS[0], "verified": "yes"}]},
        {"classes": [{**hwclasses.ROWS[0], "source": "nowhere"}]},
        {"classes": [{**hwclasses.ROWS[4], "vram_gb": None}]},
        {"classes": [hwclasses.ROWS[0], hwclasses.ROWS[0]]},
        {
            "classes": [hwclasses.ROWS[0]],
            "_sources": {hwclasses.ROWS[0]["id"]: {"url": "https://example.com/u1"}},
        },
    ],
)
def test_a_table_of_another_shape_is_refused(
    tmp_path: Path, broken: dict[str, Any]
) -> None:
    doc = {**hwclasses.document(), **broken}
    with pytest.raises(estimate.HardwareClassesError):
        estimate.load_classes(hwclasses.write(tmp_path / "classes.json", doc))


def test_the_shipped_table_sources_every_row_and_says_if_it_was_read_cleanly() -> None:
    path = estimate.classes_path()
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = estimate.load_classes(path)
    assert rows and {one.vendor for one in rows} == {"apple", "nvidia"}
    for row in raw["classes"]:
        source = raw["_sources"][row["source"]]
        said = source.get("quote") or source.get("summary")
        assert source["url"].startswith("https://") and said, row["id"]
        assert isinstance(row["verified"], bool)
    assert set(raw["_sources"]) == {row["source"] for row in raw["classes"]}


def test_no_two_shipped_rows_are_found_by_the_same_name_and_variant() -> None:
    rows = estimate.load_classes(estimate.classes_path())
    seen = [
        (estimate.class_name(one.name), one.vram_gb, one.gpu_cores, one.match_memory_gb)
        for one in rows
    ]
    assert len(seen) == len(set(seen))


def test_the_build_carries_the_table_inside_the_package() -> None:
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    force = config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    inside = f"mcgyvr/data/{estimate.CLASSES_FILENAME}"
    assert [source for source, target in force.items() if target == inside] == [
        f"data/{estimate.CLASSES_FILENAME}"
    ]
