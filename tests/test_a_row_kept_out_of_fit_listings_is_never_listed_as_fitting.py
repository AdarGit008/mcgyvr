"""A row kept out of fit listings is never listed as fitting a card.

Promises:

* A row that carries ``not_for_fit`` (a text saying why) is never among the
  rows :meth:`mcgyvr.capability.CapabilityTable.fitting` returns, at any
  memory size and any headroom, however small its memory figure.
* Every other row is listed exactly when its working footprint and the
  headroom together fit in the memory given, and the listing keeps the
  table's order: a fit listing judges memory and nothing else.
* A ``not_for_fit`` that is not non-empty text is refused by its row and the
  key, never read as a reason.

Every table here is generated (:mod:`tests.table_fixture`), with invented
model ids and numbers, asked about invented card sizes.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.capability import CapabilityTable, CapabilityTableError, load
from tests.table_fixture import CARD_SIZES, table_document, write_table

#: Invented working footprints, in no simple ratio to one another.
FOOTPRINTS = (0.8, 2.3, 4.6, 11.0, 27.5)

#: Invented headrooms, besides the one the code gives by default.
HEADROOMS = (0.0, 0.7, 3.1)


def _default_headroom() -> float:
    default = inspect.signature(CapabilityTable.fitting).parameters["headroom_gb"]
    assert isinstance(default.default, float | int)
    return float(default.default)


def _row(model_id: str, footprint: float, **extra: Any) -> dict[str, Any]:
    """A row with the keys a row needs."""
    return {
        "id": model_id,
        "family": "invented",
        "params_b": 3.0,
        "weights_gb": footprint,
        "vram_gb_working": footprint,
        **extra,
    }


def _table(tmp_path: Path) -> tuple[CapabilityTable, set[str]]:
    """A table where each footprint appears twice: kept out, and not.

    Returns the table and the ids of the rows kept out of fit listings.
    """
    rows: list[dict[str, Any]] = []
    kept_out: set[str] = set()
    for index, footprint in enumerate(FOOTPRINTS):
        kept = f"invented-kept-out-{index}"
        kept_out.add(kept)
        rows.append(_row(kept, footprint, not_for_fit="an invented reason"))
        rows.append(_row(f"invented-listed-{index}", footprint))
    document = table_document(rows=rows)
    return load(write_table(tmp_path, document)), kept_out


#: Every invented card size, a size below every row, and one above them all.
SIZES = (0.0, *CARD_SIZES, sum(FOOTPRINTS) * 10)


def test_a_row_kept_out_is_never_listed_at_any_size_or_headroom(
    tmp_path: Path,
) -> None:
    table, kept_out = _table(tmp_path)

    for size in SIZES:
        listed = {m.id for m in table.fitting(size)}
        assert not listed & kept_out, (size, sorted(listed & kept_out))
        for headroom in HEADROOMS:
            listed = {m.id for m in table.fitting(size, headroom_gb=headroom)}
            assert not listed & kept_out, (size, headroom, sorted(listed & kept_out))


def test_every_other_row_is_listed_exactly_when_it_fits_in_table_order(
    tmp_path: Path,
) -> None:
    table, kept_out = _table(tmp_path)

    for size in SIZES:
        for headroom in (_default_headroom(), *HEADROOMS):
            expected = [
                m.id
                for m in table.models
                if m.id not in kept_out and m.vram_gb_working + headroom <= size
            ]
            listed = [m.id for m in table.fitting(size, headroom_gb=headroom)]
            assert listed == expected, (size, headroom)
    roomy = [m.id for m in table.fitting(max(SIZES))]
    assert roomy == [m.id for m in table.models if m.id not in kept_out]


@pytest.mark.parametrize("given", ["", "   ", 7, True, None, ["a reason"]], ids=repr)
def test_a_reason_that_is_not_text_is_refused_by_its_row(
    tmp_path: Path, given: Any
) -> None:
    row = _row("invented-model-a", 1.9, not_for_fit=given)
    path = write_table(tmp_path, table_document(rows=[row]))

    with pytest.raises(CapabilityTableError) as refused:
        load(path)

    said = str(refused.value)
    assert "'invented-model-a'" in said, said
    assert "'not_for_fit'" in said, said
    assert str(path) in said, said
