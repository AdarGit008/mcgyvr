"""Every scoreboard row is matched to the hardware table, or says why it is not.

The fit (``tools/speed-shares/fit_shares.py``) reads each row of the CUDA
scoreboard quoted beside it and gives it one verdict: matched to one table row,
or unmatched with why (no table row of that name, the name at other memory sizes
only, two table rows under one name and size, a bandwidth or rate the row does
not state). The list is pinned here, so a row dropped or newly matched changes
the suite. Beside it, a row whose card the table names at its memory size, by
the words of the two names, must be matched, or refused as ambiguous: a row the
table holds is never left out in silence.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from types import ModuleType
from typing import Any

from tests._paths import REPO

FIT = REPO / "tools" / "speed-shares" / "fit_shares.py"
TABLE = REPO / "data" / "hardware-capabilities.json"
MATCHED, UNMATCHED = "matched", "unmatched"

#: (the row's card as the page names it, the verdict, its table row or why).
ROWS: list[tuple[str, str, str]] = [
    ("RTX 5090 32 GB", MATCHED, "nvidia-rtx-5090"),
    ("RTX PRO 6000 Blackwell 96 GB", UNMATCHED, "no table row"),
    ("H100 80 GB 80 GB", UNMATCHED, "no table row"),
    ("A100 80 GB 80 GB", UNMATCHED, "no table row"),
    ("RTX 4090 D 24 GB", UNMATCHED, "no table row"),
    ("RTX 4090 24 GB", MATCHED, "nvidia-rtx-4090"),
    ("RTX 5080 16 GB", MATCHED, "nvidia-rtx-5080"),
    ("RTX 5070 Ti 16 GB", MATCHED, "nvidia-rtx-5070-ti"),
    ("RTX 6000 Ada 48 GB", UNMATCHED, "no table row"),
    ("RTX 3090 Ti 24 GB", MATCHED, "nvidia-rtx-3090-ti"),
    ("RTX 3090 24 GB", MATCHED, "nvidia-rtx-3090"),
    ("RTX 5090 Laptop 24 GB", UNMATCHED, "no table row"),
    ("L40 48 GB", UNMATCHED, "no table row"),
    ("RTX 4080 SUPER 16 GB", MATCHED, "nvidia-rtx-4080-super"),
    ("RTX 4080 16 GB", MATCHED, "nvidia-rtx-4080"),
    ("RTX 3080 10 GB", MATCHED, "nvidia-rtx-3080-10gb"),
    ("RTX A6000 48 GB", UNMATCHED, "no table row"),
    ("RTX 4070 Ti SUPER 16 GB", MATCHED, "nvidia-rtx-4070-ti-super"),
    ("RTX PRO 4000 Blackwell 24 GB", UNMATCHED, "no table row"),
    ("RTX A5000 24 GB", UNMATCHED, "no table row"),
    ("Tesla V100 32 GB", UNMATCHED, "no table row"),
    ("RTX 5070 12 GB", MATCHED, "nvidia-rtx-5070"),
    ("A40 48 GB", UNMATCHED, "no table row"),
    ("A30 24 GB", UNMATCHED, "no table row"),
    ("Titan V 12 GB", UNMATCHED, "no table row"),
    ("RTX 2080 Ti 11 GB", MATCHED, "nvidia-rtx-2080-ti"),
    ("Quadro RTX 6000 24 GB", UNMATCHED, "no table row"),
    ("Quadro RTX 8000 48 GB", UNMATCHED, "no table row"),
    ("RTX A4500 20 GB", UNMATCHED, "no table row"),
    ("RTX 5060 Ti 16 GB", MATCHED, "nvidia-rtx-5060-ti-16gb"),
    ("RTX 2070 SUPER 8 GB", MATCHED, "nvidia-rtx-2070-super"),
    ("RTX A4000 16 GB", UNMATCHED, "no table row"),
    ("Titan Xp 12 GB", UNMATCHED, "no table row"),
    ("RTX 3060 12 GB", MATCHED, "nvidia-rtx-3060-12gb"),
    ("Quadro RTX 4000 8 GB", UNMATCHED, "no table row"),
    ("RTX 4060 Ti 8 GB", MATCHED, "nvidia-rtx-4060-ti-8gb"),
    ("GTX 1080 Ti 11 GB", MATCHED, "nvidia-gtx-1080-ti"),
    ("RTX A4000 Ada 20 GB", UNMATCHED, "no table row"),
    ("RTX 2060 SUPER 8 GB", MATCHED, "nvidia-rtx-2060-super"),
    ("Tesla P100 16 GB", UNMATCHED, "no table row"),
    ("DGX Spark 128 GB", UNMATCHED, "no table row"),
    ("Tesla P40 24 GB", UNMATCHED, "no table row"),
    ("RTX 2000 Ada 16 GB", UNMATCHED, "no table row"),
    ("Tesla T4 16 GB", UNMATCHED, "no table row"),
    ("RTX 4050 Laptop 6 GB", UNMATCHED, "no table row"),
    ("GTX 1660 6 GB", MATCHED, "nvidia-gtx-1660"),
    ("Tesla M40 24 GB", UNMATCHED, "no table row"),
    ("GTX 1070 Ti 8 GB", MATCHED, "nvidia-gtx-1070-ti"),
    ("Jetson AGX Orin 64 GB", UNMATCHED, "no table row"),
    ("Tesla P4 8 GB", UNMATCHED, "no table row"),
    ("P106-100 6 GB", UNMATCHED, "no table row"),
    ("GTX 1060 6 GB", MATCHED, "nvidia-gtx-1060-6gb"),
    ("Quadro T1000 4 GB", UNMATCHED, "no table row"),
    ("Quadro P2000 5 GB", UNMATCHED, "no table row"),
    ("Quadro P1000 4 GB", UNMATCHED, "no table row"),
    ("Tesla K80 12 GB", UNMATCHED, "no table row"),
]


def _listed() -> list[dict[str, Any]]:
    done = subprocess.run(
        [sys.executable, str(FIT), "--rows"],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    listed: list[dict[str, Any]] = json.loads(done.stdout)
    return listed


def _fit() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fit_shares", FIT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _words(name: str) -> list[str]:
    """A card's name as words, without the vendor's names and a memory size."""
    plain = re.sub(r"\(?\b\d+\s*gb\b\)?", " ", name.lower())
    words = re.split(r"[\s()]+", plain)
    return [word for word in words if word and word not in ("geforce", "nvidia")]


def test_every_row_has_the_verdict_pinned_here() -> None:
    got = [
        (one["row"], one["status"], one.get("table") or one.get("why"))
        for one in _listed()
    ]
    assert got == ROWS


def test_a_row_whose_card_the_table_names_is_never_left_out() -> None:
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    named = set()
    for row in table["rows"]:
        if row["vendor"] == "nvidia" and row["kind"] == "gpu":
            size = int(row["memory"]["size_gb"]["v"])
            named.add((tuple(_words(row["name"]["v"])), size))
    held = 0
    for one in _listed():
        card, memory, _ = one["row"].rsplit(" ", 2)
        if (tuple(_words(card)), int(memory)) not in named:
            continue
        held += 1
        assert one["status"] == MATCHED or one["why"].startswith("ambiguous"), one
    assert held == sum(1 for _, status, _ in ROWS if status == MATCHED)


def _gpu(row_id: str, name: str, size: int, bandwidth: float) -> dict[str, Any]:
    return {
        "id": row_id,
        "vendor": "nvidia",
        "kind": "gpu",
        "name": {"v": name},
        "memory": {"size_gb": {"v": size}, "bandwidth_gbps": {"v": bandwidth}},
        "compute": {"fp32_tflops": {"v": 10.0}},
        "formats": {"matrix": {"precisions": {"v": []}}},
    }


def _scoreboard(*cards: str) -> dict[str, Any]:
    return {
        "model": "llama 7B Q4_0 3.56 GiB 6.74 B",
        "rows": [
            f"{card} / GDDR6 / 128 bit 100.00 ± 1.00 10.00 ± 0.10" for card in cards
        ],
    }


def test_two_table_rows_under_one_name_and_size_are_refused_not_chosen() -> None:
    fit = _fit()
    table = {
        "rows": [
            _gpu("invented-a-gddr6", "GeForce RTX 9990", 12, 500.0),
            _gpu("invented-a-gddr6x", "GeForce RTX 9990", 12, 600.0),
        ]
    }
    got = fit.rows(_scoreboard("RTX 9990 12 GB"), table)
    assert got == [
        {
            "row": "RTX 9990 12 GB",
            "status": UNMATCHED,
            "why": "ambiguous: invented-a-gddr6, invented-a-gddr6x",
        }
    ]


def test_a_size_in_a_tables_name_is_not_part_of_the_name() -> None:
    fit = _fit()
    table = {
        "rows": [
            _gpu("invented-b-6gb", "GeForce GTX 9960 6GB", 6, 200.0),
            _gpu("invented-c-8gb", "GeForce RTX 9950 (8 GB)", 8, 300.0),
        ]
    }
    got = fit.rows(
        _scoreboard("GTX 9960 6 GB", "RTX 9950 8 GB", "RTX 9950 4 GB"), table
    )
    assert [(one["status"], one.get("table") or one.get("why")) for one in got] == [
        (MATCHED, "invented-b-6gb"),
        (MATCHED, "invented-c-8gb"),
        (UNMATCHED, "the table has it at 8 GB only"),
    ]
