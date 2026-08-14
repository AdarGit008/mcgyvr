"""The positive control, read at a tier it was not written for (#231 check 5).

Check 5 asks for *"the same battery, a different model, no redesign"*. That is a
property of the tools, not just of the runs: a control that can only be pointed
at one model forces a copy for the second tier, and once there are two copies
"no design change" is no longer something a reader can check.

Two things this file pins:

* the run directories are **arguments with pre-registered defaults**, so the
  1.5B invocation is unchanged and a second tier needs no new file;
* the reproducibility bound is **looked up per tier**, not carried as a
  constant. ``control.py`` held ``BOUND_PP = 1.47`` — the 1.5B's number — and
  annotating a 7B contrast with it is precisely the borrowing ADR-0019 D2
  forbids. A higher-pass-rate model has more cells near the acceptance boundary
  and therefore its own null.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
RUNGS = ["scope", "secrets", "structured", "adapters", "acceptance"]


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def control() -> Any:
    return _by_path("bench_control_t", REPO / "tools" / "bench" / "control.py")


@pytest.fixture(scope="module")
def report() -> Any:
    return _by_path("bench_report_ctl_t", REPO / "tools" / "bench" / "report.py")


def _manifest(model: str, tier: str, **over: Any) -> dict[str, Any]:
    base = {
        "model": model,
        "tier": tier,
        "gate_rungs": list(RUNGS),
        "serving_build": "0.32.5",
    }
    base.update(over)
    return base


def _bounds(*entries: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "bound_pp": 1.47,
            "flips": 0,
            "cells": 257,
            "runs": ["a", "b"],
            "issue": 231,
            "measured": "2026-08-13",
            **entry,
        }
        for entry in entries
    ]


def test_the_runs_are_arguments_not_constants() -> None:
    """A second tier must not need a second copy of this file.

    Run as a subprocess against ``--help`` so that argparse itself answers.
    Grepping the source would pass on a flag that was declared and never read.
    """
    done = subprocess.run(
        [sys.executable, str(REPO / "tools" / "bench" / "control.py"), "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    for flag in ("--stock", "--norule", "--sensitivity"):
        assert flag in done.stdout, (
            f"{flag} is not accepted, so a second tier forks the tool"
        )


def test_the_pre_registered_runs_remain_the_defaults(control: Any) -> None:
    """The design is fixed by the pre-registration; only the subject moves."""
    assert control.STOCK_RUN == "bench-null-gate-15b-a-2026-08-13"
    assert control.NORULE_RUN == "bench-control-norule-15b-2026-08-13"
    assert control.SENSITIVITY_RUN == "bench-null-gate-15b-b-2026-08-13"


def test_the_re_scorer_reads_the_runs_from_the_control_it_re_scores() -> None:
    """One definition, so repointing the control cannot leave the re-scorer behind.

    `lintless.py` held its own copy of the two run names. Repointing `control.py`
    at a second tier and forgetting this file would have re-scored one model's
    candidates under another's heading — and the output would have looked fine,
    because both runs exist and both parse.
    """
    lintless = _by_path("bench_lintless_t", REPO / "tools" / "bench" / "lintless.py")
    assert not hasattr(lintless, "STOCK"), "the re-scorer restates the run names"
    assert not hasattr(lintless, "NORULE")
    assert lintless.control.STOCK_RUN


def test_no_bound_is_hard_coded_in_the_control(control: Any) -> None:
    """`BOUND_PP = 1.47` was the 1.5B's, and it would have annotated any tier.

    Asserted on the module's namespace rather than its text: the docstring names
    the constant it replaced, and a grep would be satisfied by deleting the
    explanation instead of the constant.
    """
    numeric = {
        name: value
        for name, value in vars(control).items()
        if isinstance(value, float) and not name.startswith("__")
    }
    assert not numeric, (
        f"{sorted(numeric)} are module-level numbers in a tool that must read "
        "its bound per tier (ADR-0019 D2)"
    )
    assert hasattr(control, "declared_bound")


def test_a_bound_matches_only_its_own_tier(report: Any) -> None:
    bounds = _bounds(_manifest("qwen2.5-coder:1.5b", "bench-py"))
    entry, _ = report.declared_bound(
        _manifest("qwen2.5-coder:1.5b", "bench-py"), bounds
    )
    assert entry is not None
    entry, because = report.declared_bound(
        _manifest("qwen2.5-coder:7b", "bench-py"), bounds
    )
    assert entry is None
    assert "no null has been measured for qwen2.5-coder:7b" in because


def test_a_bound_does_not_transfer_across_the_serving_build(report: Any) -> None:
    """ADR-0024: a build nothing recorded has already moved results twice."""
    bounds = _bounds(_manifest("qwen2.5-coder:1.5b", "bench-py"))
    entry, because = report.declared_bound(
        _manifest("qwen2.5-coder:1.5b", "bench-py", serving_build="0.33.0"), bounds
    )
    assert entry is None
    assert "serving_build" in because
    assert "does not transfer" in because


def test_every_declared_bound_names_the_tier_it_was_measured_on(report: Any) -> None:
    """The shipped declaration, held to its own matching rule."""
    for entry in report.load_bounds():
        assert entry["tier"].startswith("bench-")
        assert entry["gate_rungs"] == RUNGS
        assert len(entry["runs"]) == 2
        assert entry["cells"] > 0


def test_the_declaration_is_valid_json_with_the_fields_a_reader_needs() -> None:
    raw = json.loads(
        (REPO / "tools" / "bench" / "reproducibility.json").read_text(encoding="utf-8")
    )
    assert raw["record"] == "reproducibility/1"
    assert raw["bounds"], "a declaration with no bounds states nothing"


def test_the_power_reports_bench_null_pools_within_a_tier_not_across(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One pooled row per model. Pooling a null across tiers is what D2 forbids.

    The pooled maps were keyed on the arm alone, so when #231 check 5 added the
    7B's pair its cells overwrote the 1.5B's and the row silently became the
    7B's under a label claiming it was everything — a defect that only appears
    once a second tier exists, which is the first thing check 5 does.
    """
    power = _by_path("power_report_t", REPO / "tools" / "power" / "report.py")
    power.bench_null()
    lines = [
        line for line in capsys.readouterr().out.splitlines() if "both arms @" in line
    ]
    models = {line.split("both arms @ ")[1].split()[0] for line in lines}
    assert len(lines) == len(models), "a pooled row per model, and no duplicates"
    assert len(models) > 1, "check 5 measured a second tier; both must be pooled"
    for line in lines:
        assert " 514 " in line, f"a pooled row must span both arms: {line!r}"
