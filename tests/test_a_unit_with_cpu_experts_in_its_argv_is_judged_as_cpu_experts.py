"""A unit that keeps experts on the CPU in its argv is judged as ``cpu_experts``.

Since #474 a locked unit's launch is ``launch.argv`` / ``env`` / ``volumes``,
verbatim (``emit`` refuses an argv that is not a list of strings). b-small's
live ``srv1_deepseek`` holds ``--n-cpu-moe``, ``19`` in its argv and has no
``n_cpu_moe`` or ``flags``, the only two fields
:func:`mcgyvr.fleet.tolerance.tolerance_class` read. So the first live probe
(2026-09-15 05:03 UTC, run-20260915T050342-42b9afd8) judged its prefill 291.55
against the lock's 307.11 (-5.1%) at llama.cpp's 1%, not CPU-experts' 48%, and
that alert pulled srv1's combination.

* ``--cpu-moe``, or ``--n-cpu-moe`` followed by a positive integer, in the argv
  is ``cpu_experts``.
* ``--n-cpu-moe 0`` stays ``llamacpp``.
* A value after ``--n-cpu-moe`` that is missing or not an integer does not
  count, as a non-positive or non-int ``n_cpu_moe`` does not. It is
  ``llamacpp``, never a crash.
* The probe's judge and the lock's NVMe check read that one class. Each judged
  field then has its own percent for it: prefill is 1% for both llama.cpp
  classes (owner, 2026-09-15), so the class shows in decode's 1% against 48%.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests import test_a_live_probe_is_judged_against_its_lock as probed

#: ``srv1_deepseek`` as ``~/.mcgyvr/fleets/b-small/fleet.yaml`` stated it on
#: 2026-09-15, with the probe tests' unit id so it fits their lock.
SRV1_DEEPSEEK: dict[str, Any] = {
    "rig": "srv1",
    "address": "http://srv1:8080",
    "engine": "llama.cpp",
    "image": "llamacpp:b10644-L3",
    "model": "deepseek-coder-v2-16b",
    "width": 2,
    "window": 8192,
    "output_tokens": 2048,
    "request_timeout_s": 180,
    "room_mib": 5458,
    "container": "mcgyvr-srv1-deepseek",
    "unit_id": probed.UNIT_DS,
    "launch": {
        "argv": [
            "--model",
            "/home/adaramir/models/moe/deepseek-coder-v2-16b.gguf",
            "--n-cpu-moe",
            "19",
            "--parallel",
            "2",
            "--port",
            "8080",
            "-b",
            "512",
            "-ub",
            "512",
            "-c",
            "8192",
            "-fa",
            "on",
            "-ngl",
            "99",
            "-t",
            "6",
        ],
        "env": {"LLAMA_ARG_HOST": "0.0.0.0"},
        "volumes": [
            "/home/adaramir/models:/models:ro",
            "/home/adaramir/models:/home/adaramir/models:ro",
        ],
    },
}


def _llamacpp(argv: object) -> dict[str, Any]:
    return {"engine": "llama.cpp", "launch": {"argv": argv}}


def _fleet_with(argv: list[str]) -> dict[str, Any]:
    """The probe tests' fleet, with deepseek launched as b-small launches it."""
    fleet: dict[str, Any] = json.loads(json.dumps(probed.FLEET))
    unit: dict[str, Any] = json.loads(json.dumps(SRV1_DEEPSEEK))
    unit["launch"]["argv"] = argv
    fleet["units"]["srv1_deepseek"] = unit
    return fleet


B_SMALL_ARGV: list[str] = list(SRV1_DEEPSEEK["launch"]["argv"])
#: b-small's argv with ``--n-cpu-moe 0`` in place of ``19``.
ZERO_ARGV = ["0" if value == "19" else value for value in B_SMALL_ARGV]


# --- the class --------------------------------------------------------------


def test_b_smalls_srv1_deepseek_is_cpu_experts() -> None:
    from mcgyvr.fleet.tolerance import tolerance_class

    assert tolerance_class(SRV1_DEEPSEEK) == "cpu_experts"


@pytest.mark.parametrize(
    "argv",
    [
        ["--model", "/models/moe/q.gguf", "-ngl", "99", "--cpu-moe", "--jinja"],
        ["--n-cpu-moe", "1"],
        ["-ngl", "99", "-t", "10", "--n-cpu-moe", "36"],
    ],
)
def test_experts_on_the_cpu_in_the_argv_is_cpu_experts(argv: list[str]) -> None:
    from mcgyvr.fleet.tolerance import tolerance_class

    assert tolerance_class(_llamacpp(argv)) == "cpu_experts"


def test_n_cpu_moe_0_in_the_argv_stays_llamacpp() -> None:
    from mcgyvr.fleet.tolerance import tolerance_class

    assert "0" in ZERO_ARGV and "19" not in ZERO_ARGV
    assert tolerance_class(_llamacpp(ZERO_ARGV)) == "llamacpp"


@pytest.mark.parametrize(
    "argv",
    [
        ["-ngl", "99", "--n-cpu-moe"],
        ["--n-cpu-moe", "--parallel", "2"],
        ["--n-cpu-moe", "nineteen"],
        ["--n-cpu-moe", "1.5"],
        ["--n-cpu-moe", ""],
        ["--n-cpu-moe", "-3"],
        ["--n-cpu-moe", "²"],
        ["--n-cpu-moe", 19],
        ["--n-cpu-moe", None],
        "--n-cpu-moe 19",
        None,
    ],
)
def test_a_malformed_n_cpu_moe_in_the_argv_is_llamacpp_not_a_crash(
    argv: object,
) -> None:
    from mcgyvr.fleet.tolerance import tolerance_class

    assert tolerance_class(_llamacpp(argv)) == "llamacpp"


def test_a_vllm_unit_is_vllm_whatever_its_argv_holds() -> None:
    from mcgyvr.fleet.tolerance import tolerance_class

    unit = {"engine": "vllm", "launch": {"argv": ["--n-cpu-moe", "19"]}}
    assert tolerance_class(unit) == "vllm"


# --- its two judges ---------------------------------------------------------


def test_the_probe_judges_b_smalls_deepseek_decode_at_cpu_experts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """30.93 against a locked 32.56 is 5.0% under: inside CPU-experts decode's
    48%, past llama.cpp decode's 1%. Prefill no longer tells the two apart: since
    the owner's 2026-09-15 ruling both llama.cpp classes judge prefill at 1%, so
    the first live probe's 291.55 alerts whichever class the argv names
    (``tests/test_prefill_is_judged_by_its_own_measured_class_tolerance.py``)."""
    monkeypatch.setattr(probed, "FLEET", _fleet_with(B_SMALL_ARGV))
    journal = probed.live_home(tmp_path, monkeypatch)
    report = probed.run_probe(probed.FakeUnits(probed.HOLDING | {"ds_decode": 30.93}))

    assert report.failed == {}
    assert report.alerts == []
    decode = [
        r
        for r in probed.rows(journal / "fleet")
        if r["unit_id"] == probed.UNIT_DS and r["field"] == "warm_decode_tok_s"
    ]
    assert [(r["observed"], r["alert"], r["tolerance_pct"]) for r in decode] == [
        (30.93, False, 48.0)
    ]


def test_the_locks_nvme_check_reads_cpu_experts_from_the_argv(tmp_path: Path) -> None:
    """30 against a 33 baseline is 9.1% slower: inside CPU-experts' 48%, past
    llama.cpp's 1%, so ``--n-cpu-moe 0`` is refused where ``19`` is locked."""
    from mcgyvr.fleet import lock

    evidence = json.loads(json.dumps(probed.EVIDENCE))
    evidence["combinations"][1]["warm_decode_tok_s"]["srv1_deepseek"] = 30.0
    evidence["combinations"][1]["baseline_tok_s"] = {"srv1_deepseek": 33.0}

    lock.write(
        tmp_path / "experts",
        _fleet_with(B_SMALL_ARGV),
        evidence,
        tolerances=probed.TOLERANCES,
    )
    with pytest.raises(lock.LockRefusedError, match="baseline"):
        lock.write(
            tmp_path / "zero",
            _fleet_with(ZERO_ARGV),
            evidence,
            tolerances=probed.TOLERANCES,
        )
