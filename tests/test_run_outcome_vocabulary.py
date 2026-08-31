"""``ok`` must mean the cell measured what it was asked for.

D8 fixed the outcome vocabulary to four values -- ok / launch_failed /
ramp_failed / refused -- so that a terminal state is stated rather than inferred
from which fields happen to be missing. One case slipped through it:
``contract.ramp`` records per-request failures as ``errors`` and returns
normally, so a ramp in which whole levels produced no successful request raises
nothing and the row keeps the ``ok`` it was constructed with.

Measured on srv1 2026-08-30. The host lost power 137 seconds into
``m_dsv2-lcpp-srv1``'s n=2 level:

    n=1   14.5 s   ok=1  errors=0                 32.8 tok/s
    n=2  327.7 s   ok=0  errors=2  TimeoutError   -- power lost mid-level
    n=4  132.4 s   ok=0  errors=4  URLError       -- host was off
    n=8  132.4 s   ok=0  errors=8  URLError       -- host was off

That cell was journalled ``ok``. ``saturation_n`` had already refused it -- "only
level n=1 survived; a curve with one point has no saturation point" -- so the
condition was computed and then not allowed to reach the field that decides
what gets re-measured. ``--resume --retry-failed`` keys on the outcome and
skipped it as good, and any ladder built from ``ok`` rows would have read one
point as a curve.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
RUN = REPO / "tools" / "bench" / "serving" / "run.py"


def _run_module() -> Any:
    """``run.py`` by path -- it is a script in a tool tree, not an installed
    package, and importing it any other way pins a layout this repo does not
    promise."""
    spec = importlib.util.spec_from_file_location("serving_run", RUN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["serving_run"] = module
    spec.loader.exec_module(module)
    return module


run_module = _run_module()


def level(n: int, ok: int, errors: int = 0, kinds: tuple[str, ...] = ()) -> dict:
    """One ramp level as ``contract.ramp`` emits it."""
    return {
        "n": n,
        "ok": ok,
        "errors": errors,
        "error_kinds": list(kinds),
        "tokens_per_s": 10.0 * n if ok else None,
    }


#: The curve srv1 actually recorded, verbatim in shape.
THE_SRV1_CELL = {
    "levels": [
        level(1, ok=1),
        level(2, ok=0, errors=2, kinds=("TimeoutError",)),
        level(4, ok=0, errors=4, kinds=("URLError",)),
        level(8, ok=0, errors=8, kinds=("URLError",)),
    ]
}

A_WHOLE_CURVE = {"levels": [level(1, 1), level(2, 2), level(4, 4), level(8, 8)]}


def test_a_whole_curve_keeps_its_outcome() -> None:
    """The negative case first, so the check below can be shown to discriminate
    rather than to refuse everything."""
    assert run_module.barren_levels(A_WHOLE_CURVE) == []
    row = {"outcome": "ok"}
    run_module.barren_downgrades_the_outcome(row, A_WHOLE_CURVE, "srv1", "cell")
    assert row["outcome"] == "ok"
    assert "refusal" not in row


def test_the_cell_that_lost_its_host_is_not_ok() -> None:
    """The case this exists for. One valid point out of four is not a curve."""
    row = {"outcome": "ok"}
    run_module.barren_downgrades_the_outcome(
        row, THE_SRV1_CELL, "srv1", "m_dsv2-lcpp-srv1"
    )
    assert row["outcome"] == "ramp_failed", (
        "a cell whose host was off for three of its four levels was recorded "
        "`ok`, and `--retry-failed` skipped it as good"
    )


def test_the_refusal_names_every_barren_level_and_what_failed() -> None:
    """A downgrade that does not say which levels died, and how, sends the
    reader back to the raw journal -- which is the shape D8 was decided
    against."""
    row: dict[str, Any] = {"outcome": "ok"}
    run_module.barren_downgrades_the_outcome(
        row, THE_SRV1_CELL, "srv1", "m_dsv2-lcpp-srv1"
    )
    prose = row["refusal"]["prose"]
    for fragment in ("n=2", "n=4", "n=8", "TimeoutError", "URLError"):
        assert fragment in prose, f"the refusal does not name {fragment}"
    assert "n=1" not in prose, "n=1 measured; naming it would misreport the cell"
    assert row["refusal"]["reasons"] == ["level_measured_nothing"]
    assert row["refusal"]["stage"] == "ramp"


@pytest.mark.parametrize("barren_n", [1, 2, 4, 8])
def test_any_single_barren_level_is_enough(barren_n: int) -> None:
    """Not just the trailing ones. A hole anywhere in the grid means the cell
    did not measure what it was asked for -- including at n=1, where a cell that
    never answered once would otherwise carry three good points and an `ok`."""
    levels = [level(n, ok=0 if n == barren_n else n) for n in (1, 2, 4, 8)]
    row = {"outcome": "ok"}
    run_module.barren_downgrades_the_outcome(row, {"levels": levels}, "srv1", "c")
    assert row["outcome"] == "ramp_failed"
    assert f"n={barren_n}" in row["refusal"]["prose"]


def test_the_downgrade_uses_a_vocabulary_word() -> None:
    """D8's four values are the whole vocabulary. A fifth invented here would
    reintroduce exactly the inference it removed."""
    row = {"outcome": "ok"}
    run_module.barren_downgrades_the_outcome(
        row, THE_SRV1_CELL, "srv1", "m_dsv2-lcpp-srv1"
    )
    assert row["outcome"] in {"ok", "launch_failed", "ramp_failed", "refused"}


def test_an_empty_ramp_is_not_silently_whole() -> None:
    """A ramp that emitted no levels at all states no rate either. It must not
    pass for want of anything to iterate."""
    assert run_module.barren_levels({}) == []
    assert run_module.barren_levels({"levels": []}) == []


def test_resume_keys_on_the_field_this_downgrades() -> None:
    """Why the outcome is the right place for this and the saturation field was
    not: ``--retry-failed`` re-measures entries whose outcome is not ``ok``, so
    a defect recorded anywhere else cannot cause a re-measurement."""
    source = RUN.read_text(encoding="utf-8")
    assert 'prior.get("outcome") != "ok"' in source, (
        "resume no longer keys on `outcome`; if it moved, this downgrade no "
        "longer causes the cell to be re-measured and must move with it"
    )


def test_a_level_that_cannot_be_read_is_not_called_barren() -> None:
    """A ramp stub may carry a bare `n` with no row behind it (there is one at
    tests/test_sink_conformance.py:1574). Judging those would refuse cells over
    the shape of their record rather than over what they measured -- and it did,
    breaking two sink-conformance tests when this check first landed."""
    assert run_module.barren_levels({"levels": [1]}) == []
    assert run_module.barren_levels({"levels": [1, {"n": 2, "ok": 0}]}) == [
        {"n": 2, "ok": 0}
    ]
