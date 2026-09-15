"""A run whose load was sampled 30 s only gets one extra cold start for room.

Owner ruling, 2026-09-15: "One extra cold start for room". ``rig-id-relock``'s
srv1-01 passed, but its load was filed before the card was sampled until idle,
so its peak covers 30 s only. It stays a valid run, and gets ONE extra entry
right after it in its rig's order: the same unit and cold start, with its own
wrapper and artifact, ``<entry>-rerun1``, whose load is sampled until idle.

* ``plan.py rerun`` refuses unless the entry is logged, passes its check, is a
  unit entry whose load was not sampled until idle, and has no re-run yet; a
  retry, a re-run, and an entry that has a retry are refused.
* The entry's re-check passes, and its re-run is the next entry to run.
* Assembly takes decode and prefill from the entry, and room and the card peak
  from its re-run; the entry's 30-s peak is kept as a lower bound. A unit with
  fewer than K valid runs sampled until idle is still refused room.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
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
)

Change = Callable[[dict[str, Any]], None]
REASON = "the load was sampled for 30 s only"
SRV1_01_REASON = (
    "load peak sampled 30 s only (filed before until-idle sampling); "
    "owner 2026-09-15: one extra cold start for room"
)
STEPS = f"tools/runs/campaigns/lock-fleets/{USE}"


def _thirty_seconds_only(payload: dict[str, Any]) -> None:
    """A load body as the harness filed it before the card was sampled to idle."""
    body = payload["doc"]["load"]["load"]
    del body["samples_before_close"], body["sampled_until_idle"]


def _failed(payload: dict[str, Any]) -> None:
    payload["doc"]["failure"] = "the unit exited before /health said ok"
    payload["doc"]["harness"] = {"error": "the unit never served"}


def _peak(entry: str, mib: int) -> Change:
    container = hashlib.sha256(entry.encode()).hexdigest()

    def change(payload: dict[str, Any]) -> None:
        sample = f"gpu_app=4242,{mib},{container},llama-server\n"
        payload["doc"]["load"]["load"]["samples"] = [sample]

    return change


def _both(*changes: Change) -> Change:
    def change(payload: dict[str, Any]) -> None:
        for one in changes:
            one(payload)

    return change


def _window_to(
    tmp_path: Path, last: str, change: dict[str, Change] | None = None
) -> Window:
    """A frozen window written, entry by entry, up to and including ``last``."""
    window = frozen_window(tmp_path)
    for entry in window.runs.entries:
        window.write(entry, (change or {}).get(entry.id))
        if entry.id == last:
            break
    return window


def test_a_rerun_is_a_wrapper_and_artifact_of_its_own_right_after_its_entry(
    tmp_path: Path,
) -> None:
    window = _window_to(tmp_path, "alpha-01", {"alpha-01": _thirty_seconds_only})
    plan = plan_module()
    made = plan.rerun(window.root, USE, "alpha-01", REASON, journal=str(window.journal))
    step = f"{STEPS}/01-{USE}-alpha-c1-a_solo-rerun1.sh"
    artifact = f"{USE}-alpha-c1-a_solo-rerun1.json"
    assert made == {
        "entry": "alpha-01",
        "reason": REASON,
        "rerun_entry": "alpha-01-rerun1",
        "artifact": artifact,
        "step": step,
    }
    listed = window.root / "records/measurements/lock-fleets" / USE / "retries.json"
    doc = json.loads(listed.read_text("utf-8"))
    assert doc["reruns"] == [made] and doc["retries"] == []
    assert "2026-09-15" in json.dumps(doc["rerun_ruling"])
    wrapper = window.root / step
    text = wrapper.read_text("utf-8")
    assert os.access(wrapper, os.X_OK)
    assert re.findall(r"^# RUN_ARTIFACTS: (.*)$", text, re.M) == [artifact]
    assert f'/../_unit.sh" {artifact} a_solo "$@"' in text

    runs = plan.read_runs(window.root, USE)
    alpha = [e.id for e in runs.entries if e.rig == "alpha"]
    assert alpha[:3] == ["alpha-01", "alpha-01-rerun1", "alpha-02"]
    base, rerun = runs.entry("alpha-01"), runs.entry("alpha-01-rerun1")
    assert (rerun.kind, rerun.units, rerun.run, rerun.fleet) == (
        "unit",
        ("a_solo",),
        "c1",
        "one",
    )
    assert (rerun.rerun_of, rerun.retry_of, rerun.wrapper) == ("alpha-01", "", step)
    assert [a for a in rerun.argv if a != step] == [
        a for a in base.argv if a != base.wrapper
    ]
    assert rerun.run_id("2026-09-16") == (
        f"2026-09-16-lock-fleets-{USE}-alpha-c1-a_solo-rerun1"
    )
    assert runs.rerun_for("alpha-01") == rerun and runs.retry_for("alpha-01") is None


REFUSALS = [
    ("alpha-01", {"alpha-01": _thirty_seconds_only}, "", "alpha-02", "has no log row"),
    (
        "alpha-01",
        {"alpha-01": _both(_thirty_seconds_only, _failed)},
        "",
        "alpha-01",
        "alpha-01 fails its check",
    ),
    (
        "alpha-02",
        {},
        "",
        "alpha-02",
        "alpha-02's load was sampled until idle",
    ),
    ("alpha-07", {}, "", "alpha-07", "only a unit entry"),
    (
        "alpha-01",
        {"alpha-01": _thirty_seconds_only},
        "rerun",
        "alpha-01",
        "alpha-01 already has a re-run, alpha-01-rerun1",
    ),
    (
        "alpha-01",
        {"alpha-01": _thirty_seconds_only},
        "rerun",
        "alpha-01-rerun1",
        "alpha-01-rerun1 is itself a re-run",
    ),
    (
        "alpha-02",
        {"alpha-02": _failed},
        "retry",
        "alpha-02-retry1",
        "alpha-02-retry1 is itself a retry",
    ),
    (
        "alpha-02",
        {"alpha-02": _failed},
        "retry",
        "alpha-02",
        "alpha-02 has a retry, alpha-02-retry1",
    ),
]


@pytest.mark.parametrize(
    ("last", "changes", "before", "entry", "said"),
    REFUSALS,
    ids=[
        "unlogged",
        "failed",
        "sampled-until-idle",
        "a-move",
        "rerun-twice",
        "a-rerun",
        "a-retry",
        "retried",
    ],
)
def test_rerun_refuses_an_entry_the_ruling_does_not_rerun(
    tmp_path: Path,
    last: str,
    changes: dict[str, Change],
    before: str,
    entry: str,
    said: str,
) -> None:
    window = _window_to(tmp_path, last, changes)
    if before == "rerun":
        window.rerun("alpha-01")
    elif before == "retry":
        window.retry("alpha-02")
    plan = plan_module()
    with pytest.raises(plan.PlanRefusedError, match=re.escape(said)):
        plan.rerun(window.root, USE, entry, REASON, journal=str(window.journal))


def _said(module: Any, argv: list[str], capsys: pytest.CaptureFixture[str]) -> Any:
    code = module.main(argv)
    return code, capsys.readouterr().out


def test_the_recheck_passes_and_the_rerun_is_the_next_entry_to_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    window = _window_to(tmp_path, "alpha-01", {"alpha-01": _thirty_seconds_only})
    plan, asm = plan_module(), assemble_module()
    root = ["--root", str(window.root)]
    journal = ["--journal", str(window.journal)]
    rerun = ["rerun", "--use", USE, "--entry", "alpha-01", "--reason", REASON]
    assert plan.main([*root, *rerun, *journal]) == 0
    capsys.readouterr()

    check = [*root, "check", "--use", USE, "--host", "alpha", "--entry", "alpha-01"]
    code, said = _said(asm, [*check, *journal], capsys)
    assert code == 0 and "alpha-01-rerun1" in said, said
    _, listed = _said(plan, [*root, "entries", "--use", USE, "--rig", "alpha"], capsys)
    order = [line.split("\t")[0] for line in listed.splitlines()]
    unlogged = [
        e
        for e in order
        if plan.main([*root, "logged", "--use", USE, "--entry", e]) != 0
    ]
    assert unlogged[:2] == ["alpha-01-rerun1", "alpha-02"]
    argv = [*root, "argv", "--use", USE, "--entry", "alpha-01-rerun1"]
    _, spelled = _said(plan, argv, capsys)
    assert f"{STEPS}/01-{USE}-alpha-c1-a_solo-rerun1.sh" in spelled.split("\0")


def test_assembly_takes_speeds_from_the_entry_and_room_from_its_rerun(
    tmp_path: Path,
) -> None:
    window = frozen_window(tmp_path)
    window.write_all({"alpha-01": _both(_thirty_seconds_only, _peak("alpha-01", 4600))})

    def rerun_run(payload: dict[str, Any]) -> None:
        _peak("alpha-01-rerun1", 4300)(payload)
        payload["doc"]["harness"]["figures"] = {
            "warm_decode_tok_s": 99.0,
            "prefill_tok_s": 200.0,
            "decode_samples": [99.0],
            "prefill_samples": [100.0, 200.0, 300.0],
        }

    window.rerun("alpha-01", rerun_run)
    evidence, runs, lines = assemble_module().assemble(context(window))

    solo = next(c for c in evidence["combinations"] if c["slots"][0][0] == "a_solo")
    assert solo["warm_decode_tok_s"] == {"a_solo": 32.0}
    assert solo["prefill_tok_s"] == {"a_solo": 310.0}
    assert solo["card_peak_mib"] == {"a_solo": 4300}
    assert "  units.a_solo.room_mib: 5000 -> 4300" in lines
    kept = runs["runs"]
    assert kept["alpha-01"]["rerun_by"] == "alpha-01-rerun1"
    base = kept["alpha-01"]["loads"]["a_solo"]
    assert (base["peak_mib"], base["peak_is_lower_bound"]) == (4600, True)
    assert kept["alpha-01-rerun1"]["rerun_of"] == "alpha-01"


def test_room_with_a_rerun_still_needs_k_runs_sampled_until_idle(
    tmp_path: Path,
) -> None:
    window = frozen_window(tmp_path)
    window.write_all(
        {"alpha-01": _thirty_seconds_only, "alpha-03": _thirty_seconds_only}
    )
    window.rerun("alpha-01")
    asm = assemble_module()
    with pytest.raises(asm.AssemblyRefusedError) as refused:
        asm.assemble(context(window))
    said = str(refused.value)
    assert "a_solo" in said and "sampled until idle" in said and "alpha-03" in said


def test_srv1_01_of_rig_id_relock_has_its_one_extra_cold_start_committed() -> None:
    plan = plan_module()
    runs = plan.read_runs(REPO, "rig-id-relock")
    srv1 = [e.id for e in runs.entries if e.rig == "srv1"]
    assert len(srv1) == 16 and srv1[:3] == ["srv1-01", "srv1-01-rerun1", "srv1-02"]
    derived, text = plan.derive_rerun("rig-id-relock", runs.entry("srv1-01"))
    assert derived == {
        "rerun_entry": "srv1-01-rerun1",
        "artifact": "rig-id-relock-srv1-c1-srv1_35b_maxctx-rerun1.json",
        "step": "tools/runs/campaigns/lock-fleets/rig-id-relock/"
        "01-rig-id-relock-srv1-c1-srv1_35b_maxctx-rerun1.sh",
    }
    listed = REPO / "records/measurements/lock-fleets/rig-id-relock/retries.json"
    doc = json.loads(listed.read_text("utf-8"))
    assert doc["reruns"] == [{"entry": "srv1-01", "reason": SRV1_01_REASON, **derived}]
    assert "2026-09-15" in json.dumps(doc["rerun_ruling"])
    assert (REPO / derived["step"]).read_text("utf-8") == text
    assert os.access(REPO / derived["step"], os.X_OK)
