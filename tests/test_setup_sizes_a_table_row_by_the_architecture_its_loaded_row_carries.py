"""Setup and the ladder read a capability row's architecture from the loaded row.

`capability.load` checks a row's `architecture` and keeps it on the `Model`;
`cli.sizing` sizes a row whose architecture is `moe` as a mixture of experts
and every other row as dense, with no second reader of the table's file.
Every row here is invented.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.capability import load
from mcgyvr.cli import sizing
from tests.table_fixture import row, table_document, write_table


def test_a_rows_moe_comes_from_the_architecture_the_loaded_row_carries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = load(
        write_table(
            tmp_path,
            table_document(
                rows=[
                    row("invented-mixture", architecture="moe"),
                    row("invented-plain", architecture="dense"),
                    row("invented-silent"),
                    {
                        **row("invented-twin", architecture="moe"),
                        "model_id": "invented-org/Invented-Twin",
                    },
                ]
            ),
        )
    )
    monkeypatch.setattr(sizing, "load", lambda: table)
    specs = {s.name: s for s in sizing._model_specs()}
    assert specs["invented-mixture"].moe is True
    assert specs["invented-plain"].moe is False
    assert specs["invented-silent"].moe is False
    assert specs["invented-twin"].moe is True
    assert specs["invented-org/Invented-Twin"].moe is True


def test_the_sizing_seam_holds_no_reader_of_its_own_for_the_table() -> None:
    assert not hasattr(sizing, "_architectures")
    assert not hasattr(sizing, "table_path")
