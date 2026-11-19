"""The shipped speed shares are what their fit gives from the inputs in the repo.

``tools/speed-shares/fit_shares.py`` reads the CUDA scoreboard's rows as quoted
beside it and the shipped hardware table, and prints the shares the product
ships. The decode shares (:data:`hubwire.DECODE_SHARES`) and the prefill shares
(:data:`estimate.PREFILL_SHARES`) must be exactly that, so no share was set by
hand.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from mcgyvr import estimate, hubwire
from tests._paths import REPO

FIT = REPO / "tools" / "speed-shares" / "fit_shares.py"
ROWS = REPO / "tools" / "speed-shares" / "scoreboard-15013.json"


def _fitted() -> dict[str, Any]:
    done = subprocess.run(
        [sys.executable, str(FIT), "--json"],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    loaded: dict[str, Any] = json.loads(done.stdout)
    return loaded


def _share(share: hubwire.FittedShare) -> dict[str, Any]:
    return {
        "value": share.value,
        "cards": share.cards,
        "low": share.low,
        "high": share.high,
        "worst": share.worst,
    }


def test_the_rows_name_the_page_they_were_quoted_from() -> None:
    rows = json.loads(ROWS.read_text(encoding="utf-8"))
    assert rows["url"] == hubwire.CUDA_SCOREBOARD
    assert rows["read"]
    assert rows["rows"]


def test_the_shipped_decode_shares_are_the_fits() -> None:
    fitted = _fitted()
    assert fitted["source"] == hubwire.CUDA_SCOREBOARD
    shipped = {
        build: {
            path: {klass: _share(share) for klass, share in classes.items()}
            for path, classes in paths.items()
        }
        for build, paths in hubwire.DECODE_SHARES.items()
    }
    assert shipped == fitted["decode"]
    for paths in hubwire.DECODE_SHARES.values():
        for classes in paths.values():
            for share in classes.values():
                assert share.source == fitted["source"]


def test_the_shipped_prefill_shares_are_the_fits() -> None:
    fitted = _fitted()
    shipped = {
        build: {path: _share(share) for path, share in paths.items()}
        for build, paths in estimate.PREFILL_SHARES.items()
    }
    assert shipped == fitted["prefill"]
    for paths in estimate.PREFILL_SHARES.values():
        for share in paths.values():
            assert share.source == fitted["source"]
