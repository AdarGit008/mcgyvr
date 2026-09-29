"""`mcgyvr capabilities` prints no score and keeps the table's order.

Promises:

* The rows are printed in the order the table gives them, never sorted by a
  figure, so the listing ranks nothing.
* A row's line carries its id, its working footprint, the one server program
  it needs when it needs one, and whether it is kept out of fit listings;
  nothing else, so no score column.
* A row that carries ``not_for_fit`` is marked "not in a fit listing", and a
  listing of what fits a card (``--vram``) leaves it out whatever the size,
  keeping the order of the rows it lists.

The invented tables are generated (:mod:`tests.table_fixture`) over more than
one shape of class set; the shipped table is read for its order only.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import capability
from mcgyvr.capability import CapabilityTable, load
from mcgyvr.cli import main
from tests.table_fixture import CLASS_SHAPES, reading, table_document, write_table

KEPT_OUT = "not in a fit listing"

#: Invented rows, in an order that is neither alphabetical nor by any figure.
ROWS: tuple[tuple[str, float, dict[str, Any]], ...] = (
    ("invented-mid", 4.4, {}),
    ("invented-big", 13.2, {"requires_backend": "some-server"}),
    ("invented-apex", 0.9, {"not_for_fit": "an invented reason"}),
    ("invented-small", 1.7, {}),
    ("invented-zeta", 6.1, {"not_for_fit": "another invented reason"}),
)


def _document(shape: str) -> dict[str, Any]:
    classes = CLASS_SHAPES[shape]
    first = str(classes[0]["id"])
    rows = [
        {
            "id": model_id,
            "family": "invented",
            "params_b": 3.0,
            "weights_gb": footprint,
            "vram_gb_working": footprint,
            "throughput_tok_s": [reading(first, value=17.0 + footprint)],
            **extra,
        }
        for model_id, footprint, extra in ROWS
    ]
    return table_document(classes=classes, rows=rows)


def _invented(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shape: str
) -> CapabilityTable:
    path = write_table(tmp_path, _document(shape))
    monkeypatch.setattr(capability, "table_path", lambda: path)
    return load(path)


def _rows(capsys: pytest.CaptureFixture[str], ids: set[str], *argv: str) -> list[str]:
    """The printed lines that are a row, in the order printed."""
    assert main(["capabilities", *argv]) == 0
    lines = capsys.readouterr().out.splitlines()
    return [line for line in lines if line.split() and line.split()[0] in ids]


def _rest(line: str, model: capability.Model) -> str:
    """What a row's line says besides its id, footprint, server and mark."""
    rest = line.replace(model.id, "", 1)
    rest = re.sub(rf"\b{model.vram_gb_working:.1f} GB\b", "", rest, count=1)
    if model.requires_backend:
        rest = rest.replace(f"[{model.requires_backend} only]", "", 1)
    return rest.replace(KEPT_OUT, "", 1).strip()


@pytest.mark.parametrize("shape", sorted(CLASS_SHAPES))
def test_the_rows_print_in_table_order_with_no_score(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    shape: str,
) -> None:
    table = _invented(tmp_path, monkeypatch, shape)
    by_id = {m.id: m for m in table.models}

    printed = _rows(capsys, set(by_id))

    assert [line.split()[0] for line in printed] == [m.id for m in table.models]
    for line in printed:
        model = by_id[line.split()[0]]
        assert _rest(line, model) == "", line
        assert (KEPT_OUT in line) == (model.not_for_fit is not None), line


@pytest.mark.parametrize("shape", sorted(CLASS_SHAPES))
def test_a_fit_listing_leaves_out_a_kept_out_row_and_keeps_the_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    shape: str,
) -> None:
    table = _invented(tmp_path, monkeypatch, shape)
    ids = {m.id for m in table.models}
    sizes = [float(c["memory_gb"]) for c in CLASS_SHAPES[shape]]

    for size in [*sizes, sum(m.vram_gb_working for m in table.models) * 3]:
        printed = [
            line.split()[0] for line in _rows(capsys, ids, "--vram", f"{size:g}")
        ]

        assert printed == [m.id for m in table.fitting(size)], size
        assert not [
            m.id for m in table.models if m.not_for_fit is not None and m.id in printed
        ], size


def test_the_shipped_rows_print_in_table_order_with_no_percentage(
    capsys: pytest.CaptureFixture[str],
) -> None:
    table = load()
    by_id = {m.id: m for m in table.models}

    printed = _rows(capsys, set(by_id))

    assert [line.split()[0] for line in printed] == [m.id for m in table.models]
    assert not [line for line in printed if "%" in line]
