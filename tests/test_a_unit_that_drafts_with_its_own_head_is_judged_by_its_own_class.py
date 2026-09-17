"""A unit that drafts with its own head is judged by its own tolerance class.

Owner ruling, 2026-09-16, after the mtp-ornith window: ``srv2_ornith_mtp`` —
a llama.cpp unit whose launch argv carries ``--spec-type draft-mtp`` — gets a
class of its own, ``mtp``, and is not judged by ``cpu_experts``' numbers. Those
were measured on srv1 offload (48% warm decode, 1% prefill), not this regime:
the unit's own three cold starts spread 1.63% in warm decode and 4.29% in
prefill, so a live probe judged by the class's 1% prefill would have failed a
sample the lock itself accepted.

* :func:`mcgyvr.fleet.tolerance.tolerance_class` puts a llama.cpp unit whose
  argv (or ``flags``) carries ``--spec-type draft-mtp`` in ``mtp``, whether or
  not experts are on the CPU beside it; any other ``--spec-type`` value, and a
  vLLM unit whatever its argv says, are judged as before.
* Every other committed unit keeps the class it had: the ruling adds a class,
  it moves nobody.
* ``tools/runs/derived.json`` states ``mtp`` in both judged fields: prefill at
  the 5% ``assemble_evidence.py tolerance`` derived from the window
  (``records/measurements/lock-fleets/mtp-ornith/prefill-tolerance-mtp.json``),
  warm decode at the same rule over the same three runs' decode samples
  (``runs.json``: L = the median of the run medians, tol = max(1, ceil(worst
  shortfall %))), which is 2%. An absent ``mtp`` is refused by name, as any
  class is.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.fleet.files import load_fleet
from mcgyvr.fleet.tolerance import (
    CLASS_CPU_EXPERTS,
    CLASS_LLAMACPP,
    CLASS_MTP,
    CLASS_VLLM,
    CLASSES,
    tolerance_class,
)

REPO = Path(__file__).resolve().parent.parent
USE = REPO / "records" / "measurements" / "lock-fleets" / "mtp-ornith"
UNIT = "srv2_ornith_mtp"
SPEC = ["--spec-type", "draft-mtp", "--spec-draft-n-max", "2"]
BASE = ["--model", "/models/moe/x.gguf", "--parallel", "1", "-c", "4096", "-ngl", "99"]

#: What every committed unit was judged as before the ruling, and still is.
BEFORE = {
    "srv2_35b_256k": CLASS_CPU_EXPERTS,
    "srv1_35b_maxctx": CLASS_CPU_EXPERTS,
    "srv2_3b": CLASS_VLLM,
    "srv2_7b": CLASS_VLLM,
    "srv2_80b": CLASS_CPU_EXPERTS,
    "srv1_deepseek": CLASS_CPU_EXPERTS,
    "srv1_35b_b": CLASS_CPU_EXPERTS,
}


def _llamacpp(argv: list[str], **launch: Any) -> dict[str, Any]:
    return {"engine": "llama.cpp", "launch": {"argv": argv, **launch}}


def committed_units() -> dict[str, Any]:
    text = (REPO / "fleet-setup" / "fleet.yaml").read_text(encoding="utf-8")
    units: dict[str, Any] = load_fleet(text)["units"]
    return units


# --- the class -------------------------------------------------------------


def test_mtp_is_a_class_of_its_own() -> None:
    assert CLASS_MTP == "mtp"
    assert CLASS_MTP in CLASSES
    assert set(CLASSES) == {CLASS_VLLM, CLASS_LLAMACPP, CLASS_CPU_EXPERTS, CLASS_MTP}


def test_the_committed_mtp_unit_is_judged_as_mtp() -> None:
    units = committed_units()
    assert "--spec-type" in units[UNIT]["launch"]["argv"]
    assert tolerance_class(units[UNIT]) == CLASS_MTP


def test_every_other_committed_unit_keeps_its_class() -> None:
    units = committed_units()
    assert set(units) == {*BEFORE, UNIT}
    assert {name: tolerance_class(units[name]) for name in BEFORE} == BEFORE


@pytest.mark.parametrize(
    "argv",
    [
        [*BASE, *SPEC],
        [*BASE[:2], "--n-cpu-moe", "8", *SPEC, *BASE[2:]],
        [*BASE, "--cpu-moe", *SPEC],
        [*SPEC, *BASE],
    ],
)
def test_draft_mtp_in_the_argv_is_mtp_with_or_without_experts_on_the_cpu(
    argv: list[str],
) -> None:
    assert tolerance_class(_llamacpp(argv)) == CLASS_MTP


def test_draft_mtp_among_the_flags_is_mtp() -> None:
    unit = {"engine": "llama.cpp", "launch": {"flags": SPEC}}
    assert tolerance_class(unit) == CLASS_MTP


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (
            [*BASE, "--spec-type", "draft-model", "--spec-draft-n-max", "2"],
            CLASS_LLAMACPP,
        ),
        ([*BASE, "--n-cpu-moe", "8", "--spec-type", "ngram"], CLASS_CPU_EXPERTS),
        ([*BASE, "--spec-type"], CLASS_LLAMACPP),
        ([*BASE, "draft-mtp"], CLASS_LLAMACPP),
        ([*BASE, "--spec-draft-n-max", "2"], CLASS_LLAMACPP),
    ],
)
def test_any_other_spec_type_or_a_bare_word_is_judged_as_before(
    argv: list[str], expected: str
) -> None:
    assert tolerance_class(_llamacpp(argv)) == expected


def test_a_vllm_unit_is_vllm_whatever_its_argv_says() -> None:
    unit = {"engine": "vllm", "launch": {"argv": ["Qwen/x", *SPEC]}}
    assert tolerance_class(unit) == CLASS_VLLM


# --- the numbers ----------------------------------------------------------------


def _derived() -> dict[str, dict[str, float]]:
    from mcgyvr import derived

    return derived.class_tolerances()


def test_mtp_prefill_is_the_tolerance_the_window_derived() -> None:
    doc = json.loads((USE / "prefill-tolerance-mtp.json").read_text(encoding="utf-8"))
    assert doc["unit"] == UNIT and doc["class"] == CLASS_MTP
    assert doc["tolerance_pct"] == 5
    assert _derived()["prefill_tok_s"][CLASS_MTP] == 5.0


def test_mtp_warm_decode_is_the_same_rule_over_the_same_three_runs() -> None:
    runs = json.loads((USE / "runs.json").read_text(encoding="utf-8"))["runs"]
    figures = [
        run["figures"][UNIT]
        for run in runs.values()
        if run["kind"] == "unit" and run["units"] == [UNIT] and "retried_by" not in run
    ]
    assert len(figures) == 3
    locked = statistics.median([f["warm_decode_tok_s"] for f in figures])
    samples = [s for f in figures for s in f["decode_samples"]]
    assert len(samples) == 15
    worst = max(max(0.0, (locked - s) / locked * 100.0) for s in samples)
    assert 1.0 < worst < 2.0
    assert _derived()["warm_decode_tok_s"][CLASS_MTP] == float(max(1, math.ceil(worst)))
    assert _derived()["warm_decode_tok_s"][CLASS_MTP] == 2.0


def test_the_other_classes_numbers_did_not_move() -> None:
    tolerances = _derived()
    decode = {
        k: v for k, v in tolerances["warm_decode_tok_s"].items() if k != CLASS_MTP
    }
    prefill = {k: v for k, v in tolerances["prefill_tok_s"].items() if k != CLASS_MTP}
    assert decode == {"vllm": 1.0, "llamacpp": 1.0, "cpu_experts": 48.0}
    assert prefill == {"vllm": 8.0, "llamacpp": 1.0, "cpu_experts": 1.0}


@pytest.mark.parametrize("entry", ["warm_decode_class_pct", "prefill_class_pct"])
def test_an_absent_mtp_class_is_refused_by_name(entry: str, tmp_path: Path) -> None:
    from mcgyvr import derived

    doc = json.loads((REPO / "tools/runs/derived.json").read_text(encoding="utf-8"))
    del doc["engine"][entry][CLASS_MTP]
    path = tmp_path / "derived.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(derived.DerivedNumbersError, match=entry) as was:
        derived.class_tolerances(path=path)
    assert repr(CLASS_MTP) in str(was.value)
