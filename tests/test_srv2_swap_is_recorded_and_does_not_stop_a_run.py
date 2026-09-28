"""srv2's swap growth is recorded and does not stop a run.

The owner's ruling "Record swap on srv2 too" is filed with its evidence: the
run it is about, ``srv2-01-relaunch1`` (unit ``srv2_35b_256k``), which ran
clean except for a ``pswpout`` rise of a few pages, and the measurement that
unit's pin was locked from
(``records/measurements/fleet-setup-2026-09-13/srv2/a-solo-running.json``),
which moved more swap than that run did.

So ``rig-id-relock``'s ``use.json`` lists srv2 beside srv1 in
``swap_recorded_not_stopped_on`` — the same mechanism, not a second one. On
either listed rig a run's pswpout start, end and delta are filed and its growth
is no reason to stop; a marker that differs, restarts above 0, a failed step
and every other refusal still stop the run on both, and a rig the use does not
list keeps the swap stop. Swap is filed as data: never judged, and never a
reason to call a run invalid.

No rig is reached: every run here is a fixture in a throw-away tree.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.lockfleets_window import (
    REPO,
    USE,
    Window,
    assemble_module,
    context,
    frozen_window,
    plan_module,
    use_doc,
)

Change = Callable[[dict[str, Any]], None]

#: The owner's words.
SAID = "Record swap on srv2 too"
USE_PATH = REPO / "records/measurements/lock-fleets/rig-id-relock/use.json"
README = REPO / "records/measurements/lock-fleets/README.md"
#: The 09-13 measurement srv2_35b_256k's pin was locked from.
PRECEDENT = "records/measurements/fleet-setup-2026-09-13/srv2/a-solo-running.json"
#: Its vmstat delta: more swap than srv2-01-relaunch1 moved.
PRECEDENT_PAGES = 295

#: srv2-01-relaunch1's own pswpout reading, and the 100 pages between them.
START, END = 91686, 91786
PAGES = END - START
#: What else that run filed.
WAKE_S = 8.202
DECODE_SAMPLES = [48.20, 49.00, 49.22, 49.50, 50.10]
DECODE = 49.22
PREFILL_SAMPLES = [623.47, 632.02, 634.98]
PREFILL = 632.02
CARD_PEAK = 10564

#: The stop swap growth gives on a rig the use does not list.
SWAP = "pswpout rose during the run"

#: The fixture rig that stands in for each rig of the committed use: alpha
#: takes turns between two llama.cpp units as srv1 does; beta is the fixture's
#: pinned, capped rig and serves a pair, as srv2 does.
STANDS_IN = {"srv1": "alpha", "srv2": "beta"}
#: A unit run of each fixture rig — the kind of entry that files a pswpout.
UNIT_ENTRY = {"alpha": "alpha-02", "beta": "beta-01"}
UNIT_NAME = {"alpha": "a_pair", "beta": "b_big"}


def listed() -> tuple[str, ...]:
    """The rigs the committed use records swap on, rather than stopping."""
    use = plan_module().load_use(REPO, "rig-id-relock")
    return tuple(str(rig) for rig in use.swap_recorded_not_stopped_on)


def fixture_use() -> dict[str, Any]:
    """A made-up use that lists the stand-in of every rig the committed one does."""
    return use_doc(swap_recorded_not_stopped_on=[STANDS_IN[r] for r in listed()])


def _swapped(payload: dict[str, Any]) -> None:
    """A run that moved 100 pages of swap, as srv2-01-relaunch1 did."""
    vmstat = payload["doc"]["vmstat"]
    vmstat["start"]["pswpout"] = START
    vmstat["end"]["pswpout"] = END


def _like_relaunch1(payload: dict[str, Any]) -> None:
    """A clean campaign unit run shaped like srv2-01-relaunch1: exit 0, no
    failure, restarts 0, identical START/END markers, a load sampled until
    idle, and only the 100 pages of swap against it."""
    _swapped(payload)
    doc = payload["doc"]
    doc["failure"] = None
    doc["restarts"] = 0
    doc["wake_s"] = WAKE_S
    figures = doc["harness"]["figures"]
    figures["warm_decode_tok_s"] = DECODE
    figures["decode_samples"] = list(DECODE_SAMPLES)
    figures["prefill_tok_s"] = PREFILL
    figures["prefill_samples"] = list(PREFILL_SAMPLES)
    body = doc["load"]["load"]
    body["samples"] = [
        f"gpu_app=4242,{mib},{doc['container_id']},llama-server\n"
        for mib in (CARD_PEAK - 300, CARD_PEAK)
    ]
    body["sampled_until_idle"] = True


def _rebooted(payload: dict[str, Any]) -> None:
    """The same run, on a rig whose uptime moved between START and END."""
    _swapped(payload)
    payload["doc"]["markers"]["end"] = (
        "### END uptime_since=2026-09-16T11:00:00Z "
        "pl1_uw=95000000 pl2_uw=120000000 ram_mt_s=3600"
    )


def _restarted(payload: dict[str, Any]) -> None:
    _swapped(payload)
    payload["doc"]["restarts"] = 1


def _failed(payload: dict[str, Any]) -> None:
    _swapped(payload)
    payload["doc"]["failure"] = "the unit exited before /health said ok"


@pytest.fixture
def window(tmp_path: Path) -> Window:
    return frozen_window(tmp_path, use=fixture_use())


# --------------------------------------------------------------------------
# what the repo commits
# --------------------------------------------------------------------------


def test_the_use_records_swap_on_both_of_its_rigs() -> None:
    assert listed() == ("srv1", "srv2")
    doc = json.loads(USE_PATH.read_text("utf-8"))
    assert doc["swap_recorded_not_stopped_on"] == ["srv1", "srv2"]


def test_the_use_says_why_srv2_joined_srv1() -> None:
    """The note carries the owner's words, the run's own numbers, the 09-13
    precedent with its path, and what else that run filed."""
    why = json.loads(USE_PATH.read_text("utf-8"))["_swap_recorded_not_stopped_on"]
    assert "2026-09-16" in why and SAID in why, why
    assert str(START) in why and str(END) in why, why
    assert "100 pages" in why, why
    assert PRECEDENT in why and str(PRECEDENT_PAGES) in why, why
    assert "exit 0" in why and "restarts 0" in why, why
    assert "START" in why and "END" in why, why


def test_srv1s_2026_09_15_ruling_is_still_recorded() -> None:
    """The 09-16 ruling extends the 09-15 one; it does not replace it."""
    why = json.loads(USE_PATH.read_text("utf-8"))["_swap_recorded_not_stopped_on"]
    assert "2026-09-15" in why and "Record swap on srv1, don't stop" in why, why
    assert "ram-headroom-2026-09-09" in why, why
    assert "264920" in why and "312345" in why, why


def test_the_readme_records_the_srv2_ruling_with_its_citations() -> None:
    readme = README.read_text("utf-8")
    assert "2026-09-16" in readme and SAID in readme
    assert f"{START} -> {END}" in readme or f"{START} → {END}" in readme
    assert "100 pages" in readme
    assert PRECEDENT in readme
    assert str(PRECEDENT_PAGES) in readme
    # The 09-15 entry it extends is still there, with its own citation. The
    # README wraps its prose, so the srv1 quote is matched by its tail.
    assert "on srv1, don't stop" in readme
    assert "ram-headroom-2026-09-09" in readme


# --------------------------------------------------------------------------
# the run the ruling is about
# --------------------------------------------------------------------------


def test_a_run_shaped_like_srv2_01_relaunch1_passes_and_files_its_swap(
    window: Window,
) -> None:
    rig, entry = STANDS_IN["srv2"], UNIT_ENTRY[STANDS_IN["srv2"]]
    window.write_all({entry: _like_relaunch1})
    asm = assemble_module()
    ctx = context(window)
    assert asm.check(ctx, rig, entry) == []
    _, runs, _ = asm.assemble(ctx)
    run = runs["runs"][entry]
    assert run["pswpout"] == {"start": START, "end": END, "delta": PAGES}
    # Filed as data beside the numbers the run was for, and not as a verdict:
    # a run that gives no reason to stop carries no reasons at all.
    assert "check" not in run
    load = run["loads"][UNIT_NAME[rig]]
    assert load["peak_mib"] == CARD_PEAK
    assert load["sampled_until_idle"] is True


@pytest.mark.parametrize("real", ["srv1", "srv2"])
def test_swap_on_a_listed_rig_is_filed_and_does_not_stop(
    window: Window, real: str
) -> None:
    rig = STANDS_IN[real]
    entry = UNIT_ENTRY[rig]
    window.write_all({entry: _swapped})
    asm = assemble_module()
    ctx = context(window)
    assert asm.check(ctx, rig, entry) == []
    _, runs, _ = asm.assemble(ctx)
    assert runs["runs"][entry]["pswpout"] == {
        "start": START,
        "end": END,
        "delta": PAGES,
    }


def test_both_rigs_may_swap_in_one_window_and_the_window_still_assembles(
    window: Window,
) -> None:
    entries = {UNIT_ENTRY[STANDS_IN[real]]: _swapped for real in ("srv1", "srv2")}
    window.write_all(entries)
    asm = assemble_module()
    _, runs, _ = asm.assemble(context(window))
    for entry in entries:
        assert runs["runs"][entry]["pswpout"]["delta"] == PAGES
        assert "check" not in runs["runs"][entry]


# --------------------------------------------------------------------------
# everything else still stops, on both rigs
# --------------------------------------------------------------------------


STILL_STOPS: list[tuple[str, Change, str]] = [
    ("a marker", _rebooted, "the START and END markers differ: uptime_since"),
    ("restarts", _restarted, "restarted 1 time(s)"),
    ("a failure", _failed, "the step failed"),
]


@pytest.mark.parametrize("real", ["srv1", "srv2"])
@pytest.mark.parametrize(
    ("what", "change", "said"), STILL_STOPS, ids=[s[0] for s in STILL_STOPS]
)
def test_every_other_stop_still_applies_on_a_listed_rig(
    window: Window, real: str, what: str, change: Change, said: str
) -> None:
    rig = STANDS_IN[real]
    entry = UNIT_ENTRY[rig]
    window.write_all({entry: change})
    reasons = assemble_module().check(context(window), rig, entry)
    assert any(said in why for why in reasons), (what, reasons)
    # The swap that came with it is filed, and is not one of the reasons.
    assert not any(SWAP in why for why in reasons), reasons


def test_a_rig_the_use_does_not_list_keeps_the_swap_stop(tmp_path: Path) -> None:
    """Listing is per rig and per use: nothing here is global."""
    unlisted = frozen_window(
        tmp_path, use=use_doc(swap_recorded_not_stopped_on=["alpha"])
    )
    unlisted.write_all({"beta-01": _swapped})
    reasons = assemble_module().check(context(unlisted), "beta", "beta-01")
    assert f"{SWAP} ({START} -> {END})" in reasons, reasons


def test_the_planner_reads_every_rig_the_use_lists(tmp_path: Path) -> None:
    plan = plan_module()
    root = frozen_window(tmp_path, use=fixture_use()).root
    use = plan.load_use(root, USE)
    assert use.swap_recorded_not_stopped_on == tuple(
        STANDS_IN[real] for real in listed()
    )
