"""The capability table is shipped data that sizing and listing rest on.

These tests hold the shipped table to the properties `mcgyvr capabilities` and
`mcgyvr emit` rely on, and hold the fit listing to its rule over generated
tables.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from mcgyvr.capability import CapabilityTable, CapabilityTableError, load, table_path
from tests.table_fixture import row, table_document, write_table


def test_shipped_table_loads() -> None:
    table = load()
    assert table.models
    assert table.caveats, "the known-bad measurement caveats must travel with the data"


def test_every_model_has_a_working_footprint() -> None:
    for model in load().models:
        assert model.vram_gb_working > 0, f"{model.id} has no working VRAM figure"


#: Invented working footprints, and invented headrooms besides the default.
FOOTPRINTS = (1.3, 3.9, 8.2)
HEADROOMS = (0.4, 2.6)


def _default_headroom() -> float:
    default = inspect.signature(CapabilityTable.fitting).parameters["headroom_gb"]
    assert isinstance(default.default, float | int)
    return float(default.default)


def _invented(tmp_path: Path) -> CapabilityTable:
    rows = [
        row(f"invented-model-{index}", vram_gb_working=footprint)
        for index, footprint in enumerate(FOOTPRINTS)
    ]
    return load(write_table(tmp_path, table_document(rows=rows)))


def test_marginal_fits_are_excluded(tmp_path: Path) -> None:
    """CAV-04: a model that only just fits degrades rather than failing.

    A card with less free room than the headroom beside a row's working
    footprint is not offered that row, however close the fit.
    """
    table = _invented(tmp_path)
    for headroom in (_default_headroom(), *HEADROOMS):
        for model in table.models:
            just_short = model.vram_gb_working + headroom * 0.9
            enough = model.vram_gb_working + headroom
            short_ids = {m.id for m in table.fitting(just_short, headroom_gb=headroom)}
            assert model.id not in short_ids
            assert model.id in {
                m.id for m in table.fitting(enough, headroom_gb=headroom)
            }


def test_headroom_is_absolute_not_proportional(tmp_path: Path) -> None:
    """No share of the card separates what is listed from what is not.

    What the headroom reserves, KV cache for the context window, is sized by
    tokens, not by the card. So a small row is refused on a card it would fill
    by a small share when the room beside it is short, while a large row is
    listed on a card it nearly fills when the room is there: a rule by share
    of the card would have to admit the first to admit the second.
    """
    table = _invented(tmp_path)
    headroom = _default_headroom()
    listed_shares: list[float] = []
    refused_shares: list[float] = []
    for model in table.models:
        enough = model.vram_gb_working + headroom
        short = model.vram_gb_working + headroom * 0.9
        assert model in table.fitting(enough)
        assert model not in table.fitting(short)
        listed_shares.append(model.vram_gb_working / enough)
        refused_shares.append(model.vram_gb_working / short)

    assert max(listed_shares) > min(refused_shares)


def test_rejects_unknown_schema_version(tmp_path: Path) -> None:
    raw = json.loads(table_path().read_text(encoding="utf-8"))
    raw["schema_version"] = 99
    bad = tmp_path / "capability-table.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CapabilityTableError, match="schema_version"):
        load(bad)


def test_rejects_malformed_json(tmp_path: Path) -> None:
    bad = tmp_path / "capability-table.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(CapabilityTableError, match="not valid JSON"):
        load(bad)


def test_rejects_table_with_no_models(tmp_path: Path) -> None:
    document = table_document()
    document["models"] = []
    bad = write_table(tmp_path, document)
    with pytest.raises(CapabilityTableError, match="no models"):
        load(bad)
