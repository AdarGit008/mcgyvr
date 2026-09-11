"""The measuring-gaps ``C`` reports reproduce from any clone of this repository.

``c_drift_report.py`` named ``/home/adaramir/claude/mcgyvr/records/...`` for its
geometry and ``q6_report.py`` named the ``mcgyvr-fleet-id`` checkout: absolute
paths into one machine's checkouts, so neither report ran anywhere else, and
Q6's README had to say so. The scan both read,
``records/measurements/ram-headroom-2026-09-09/deepseek.geometry.json``, has
been in the tree since ``cde08e60``.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
RUN = REPO / "records" / "measurements" / "measuring-gaps-2026-09-10"


def _load(script: str, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import a report without letting its ``sys.path`` edit outlive the test."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    spec = importlib.util.spec_from_file_location(
        f"_mg_{Path(script).stem}", RUN / script
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("script", ["c_drift_report.py", "q6_report.py"])
def test_a_report_reads_a_geometry_this_checkout_carries(
    script: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    geometry = Path(_load(script, monkeypatch).GEOM_PATH).resolve()
    assert geometry.is_relative_to(REPO), geometry
    assert geometry.is_file(), geometry


def _run(
    script: str,
    rows: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    """Run a report on a copy of its committed rows, so the tree is not rewritten."""
    module = _load(script, monkeypatch)
    copy = tmp_path / rows
    shutil.copyfile(RUN / rows, copy)
    monkeypatch.setattr(sys, "argv", [script, str(copy)])
    module.main()
    report: dict[str, Any] = json.loads(
        copy.with_name(copy.stem + "-report.json").read_text()
    )
    return report


def test_the_q4_report_reproduces_its_committed_constants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    got = _run(
        "c_drift_report.py", "results-arms-q4-c-drift.json", tmp_path, monkeypatch
    )
    kept = json.loads((RUN / "results-arms-q4-c-drift-report.json").read_text())
    assert [a["C_mib"] for a in got["arms"]] == [a["C_mib"] for a in kept["arms"]]
    assert (got["C_min_mib"], got["C_max_mib"]) == (3028.0, 3102.0)


def test_the_q6_report_reproduces_its_committed_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    got = _run(
        "q6_report.py", "results-arms-q6-no-op-offload.json", tmp_path, monkeypatch
    )
    kept = json.loads((RUN / "results-arms-q6-no-op-offload-report.json").read_text())
    assert got["C_probe_n0_mib"] == kept["C_probe_n0_mib"] == 3028.0
    assert got["groups"] == kept["groups"]
