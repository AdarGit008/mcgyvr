"""The shipped hardware table is what its build gives from the inputs in the repo.

``tools/hardware-table/build_db.py`` merges the wave files beside it into the
table, offline (it reads no page). Run on its build date, it must give the
shipped file byte for byte, so no cell of the shipped table was set by hand.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mcgyvr import hardware_table
from tests._paths import REPO

BUILD = REPO / "tools" / "hardware-table" / "build_db.py"
SHIPPED = REPO / "data" / hardware_table.TABLE_FILENAME


def _build(tmp_path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    built = json.loads(SHIPPED.read_text(encoding="utf-8"))["built"]
    return subprocess.run(
        [sys.executable, str(BUILD), "--built", built, *extra],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def test_the_build_gives_the_shipped_table_byte_for_byte(tmp_path: Path) -> None:
    out = tmp_path / hardware_table.TABLE_FILENAME
    done = _build(tmp_path, "--out", str(out))
    assert done.returncode == 0, done.stdout + done.stderr
    assert out.read_bytes() == SHIPPED.read_bytes()


def test_the_quoted_table_keeps_a_quote_for_every_value(tmp_path: Path) -> None:
    out, quoted = tmp_path / "shipped.json", tmp_path / "quoted.json"
    done = _build(tmp_path, "--out", str(out), "--quoted", str(quoted))
    assert done.returncode == 0, done.stdout + done.stderr
    full = json.loads(quoted.read_text(encoding="utf-8"))
    bare = []

    def walk(node: object, at: str) -> None:
        if isinstance(node, dict) and "v" in node:
            value = node["v"]
            empty = value is None or value is False or value == []
            if not empty and not node.get("quote"):
                bare.append(at)
        elif isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{at}.{key}")

    for row in full["rows"]:
        walk(row, row["id"])
    assert not bare, bare[:20]
