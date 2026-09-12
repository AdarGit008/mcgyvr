"""The per-rig derived-numbers file, and the code held to it.

``tools/runs/derived.json`` is the single source of truth for the numeric
values mcgyvr measures on a rig rather than reads from the rig or from the
model: the runtime-resident intercept host-RAM sizing adds to spilled experts,
the per-rig card remainder ``vramfit``'s ``C`` subsumes, and the engine-specific
warm-decode tolerances the fleet lock weighs NVMe against.

This file holds the file to the same contract ``test_declared_host_state.py``
holds ``tools/runs/hosts.json`` to — every number states a value and why it is
that value, and an absent number is a named refusal, never a silent inline
default — and it holds the code to the file: the moved literals appear only
here, never as a source-of-truth literal in ``src/``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import derived

REPO = Path(__file__).resolve().parent.parent
DERIVED = REPO / "tools" / "runs" / "derived.json"
SRC = REPO / "src"


def document() -> dict[str, Any]:
    loaded = json.loads(DERIVED.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), "the derived-numbers file is not a JSON object"
    return loaded


def _unexplained(numbers: dict[str, Any]) -> list[str]:
    """Which entries state no value or no reason, mirroring the host-state check."""
    return sorted(
        name
        for name, body in numbers.items()
        if not isinstance(body, dict)
        or not str(body.get("value", "")).strip()
        or not str(body.get("why", "")).strip()
    )


def test_every_host_names_its_derived_numbers() -> None:
    doc = document()
    assert set(doc["hosts"]) == {"srv1", "srv2"}
    for host in doc["hosts"]:
        assert isinstance(doc[host], dict), host
        assert isinstance(doc[host].get("numbers"), dict), host


def test_every_number_states_a_value_and_why_it_is_that_value() -> None:
    doc = document()
    for host in doc["hosts"]:
        unexplained = _unexplained(doc[host]["numbers"])
        assert not unexplained, (
            f"{host} carries derived numbers without a value or a reason: {unexplained}"
        )
    unexplained = _unexplained(doc["engine"]["warm_decode_pct"])
    assert not unexplained, (
        f"engine tolerances without a value or a reason: {unexplained}"
    )


def test_the_runtime_resident_intercept_resolves_for_each_rig() -> None:
    assert derived.runtime_resident_gb("srv1") == pytest.approx(1.53)
    assert derived.runtime_resident_gb("srv2") == pytest.approx(1.53)


def test_the_engine_tolerances_resolve() -> None:
    assert derived.warm_decode_tolerances() == {"vllm": 3.0, "llama.cpp": 5.0}


def test_the_per_rig_card_remainder_is_recorded() -> None:
    doc = document()
    assert doc["srv1"]["numbers"]["card_remainder_mib"]["value"] == 97.69
    assert doc["srv2"]["numbers"]["card_remainder_mib"]["value"] == 144.67


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


def test_a_missing_engine_tolerance_is_refused_by_name(tmp_path: Path) -> None:
    mutated = json.loads(DERIVED.read_text(encoding="utf-8"))
    del mutated["engine"]["warm_decode_pct"]
    path = tmp_path / "derived.json"
    path.write_text(json.dumps(mutated), encoding="utf-8")
    with pytest.raises(derived.DerivedNumbersError, match="warm_decode_pct"):
        derived.warm_decode_tolerances(path=path)


def test_the_moved_literals_live_only_in_the_file() -> None:
    """The numbers that were hard-coded in ``src/`` are gone from it."""
    serving = (SRC / "mcgyvr" / "serving" / "__init__.py").read_text(encoding="utf-8")
    cli = (SRC / "mcgyvr" / "cli.py").read_text(encoding="utf-8")
    vramfit = (SRC / "mcgyvr" / "serving" / "vramfit.py").read_text(encoding="utf-8")
    assert "RUNTIME_RESIDENT_GB" not in serving
    assert "1.53" not in serving
    assert "144.67" not in vramfit and "97.69" not in vramfit
    assert '"vllm": 3.0' not in cli and '"llama.cpp": 5.0' not in cli
    assert "warm_decode_tolerances()" in cli


def test_the_runtime_resident_constant_is_gone() -> None:
    from mcgyvr import serving

    assert not hasattr(serving, "RUNTIME_RESIDENT_GB")
