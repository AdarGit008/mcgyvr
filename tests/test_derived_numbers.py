"""The per-rig derived-numbers file, and the code held to it.

``tools/runs/derived.json`` is the single source of truth for the numeric
values mcgyvr measures on a rig rather than reads from the rig or from the
model: the runtime-resident intercept host-RAM sizing adds to spilled experts,
the per-rig card remainder ``vramfit``'s ``C`` subsumes, and the class
tolerances the fleet lock weighs NVMe against and a live probe is judged by.

This file holds the file to the same contract ``test_declared_host_state.py``
holds ``tools/runs/hosts.json`` to — every number states a value and why it is
that value, and an absent number is a named refusal, never a silent inline
default — and it holds the code to the file: the moved literals appear only
here, never as a source-of-truth literal in ``src/``. The class tolerances'
own resolution and refusal are in
``tests/test_a_live_probe_is_judged_against_its_lock.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcgyvr import derived

REPO = Path(__file__).resolve().parent.parent
DERIVED = REPO / "tools" / "runs" / "derived.json"
SRC = REPO / "src"


def test_a_rig_whose_number_is_absent_is_refused_by_name(tmp_path: Path) -> None:
    mutated = json.loads(DERIVED.read_text(encoding="utf-8"))
    del mutated["srv2"]["numbers"]["runtime_resident_gb"]
    path = tmp_path / "derived.json"
    path.write_text(json.dumps(mutated), encoding="utf-8")
    with pytest.raises(derived.DerivedNumbersError, match="runtime_resident_gb"):
        derived.runtime_resident_gb("srv2", path=path)


def test_a_rig_that_is_not_declared_is_refused_by_name() -> None:
    with pytest.raises(derived.DerivedNumbersError, match="desktop-2"):
        derived.runtime_resident_gb("desktop-2")


def test_the_moved_literals_live_only_in_the_file() -> None:
    """The numbers that were hard-coded in ``src/`` are gone from it."""
    serving = (SRC / "mcgyvr" / "serving" / "__init__.py").read_text(encoding="utf-8")
    cli = (SRC / "mcgyvr" / "cli.py").read_text(encoding="utf-8")
    vramfit = (SRC / "mcgyvr" / "serving" / "vramfit.py").read_text(encoding="utf-8")
    assert "RUNTIME_RESIDENT_GB" not in serving
    assert "1.53" not in serving
    assert "144.67" not in vramfit and "97.69" not in vramfit
    assert '"vllm": 3.0' not in cli and '"llama.cpp": 5.0' not in cli
    assert '"cpu_experts": 48.0' not in cli
    assert "class_tolerances()" in cli


def test_the_runtime_resident_constant_is_gone() -> None:
    from mcgyvr import serving

    assert not hasattr(serving, "RUNTIME_RESIDENT_GB")
