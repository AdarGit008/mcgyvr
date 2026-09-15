"""lock-fleets judges a load's card peak over every sample up to idle.

Owner ruling, 2026-09-15: "Sample the card until idle". ``rig-id-relock``'s
srv1-01 closed its load's request at 30 s and llama.cpp b10644 went on working:
``idle_after_close`` false, ``idle_after_s`` 104.3, and all 58 card samples
taken before the close. So:

* a unit's room and card peak are the max of its loads' peaks over every sample
  up to idle, with ``peak_before_close_mib`` and ``sampled_until_idle`` filed
  beside each;
* a load not sampled until idle (one filed before this ruling) is kept as a data
  point with its peak a lower bound. ``check`` does not stop on it, but a unit's
  room is refused, naming those runs, while fewer than K of its valid runs were
  sampled until idle: whether such a run may count is an open owner question;
* the stop on ``idle_after_close`` false on a rig's first long-context run is
  gone. That question is answered, and the flag stays filed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from tests.lockfleets_window import (
    PEAK,
    Window,
    assemble_module,
    context,
    frozen_window,
    use_doc,
)


def _busy_after_close(payload: dict[str, Any]) -> None:
    body = payload["doc"]["load"]["load"]
    body |= {"idle_after_close": False, "idle_after_s": 104.3}


def _not_sampled_until_idle(payload: dict[str, Any]) -> None:
    """A load body as the harness filed it before the ruling."""
    body = payload["doc"]["load"]["load"]
    del body["samples_before_close"], body["sampled_until_idle"]


def _row_not_sampled_until_idle(payload: dict[str, Any]) -> None:
    row = payload["units"]["b_small"]["load_peak_mib"]
    del row["peak_before_close_mib"], row["samples_before_close"]
    del row["sampled_until_idle"]


def _like_srv1_01(payload: dict[str, Any]) -> None:
    _not_sampled_until_idle(payload)
    _busy_after_close(payload)
    payload["doc"]["load"]["load"] |= {"completed": 0, "closed_unfinished": 1}
    payload["doc"]["vmstat"]["start"]["pswpout"] = 264920
    payload["doc"]["vmstat"]["end"]["pswpout"] = 312345


@pytest.fixture
def window(tmp_path: Path) -> Window:
    return frozen_window(tmp_path)


@pytest.mark.parametrize("entry", ["alpha-01", "beta-01"])
def test_check_no_longer_stops_on_a_unit_still_busy_after_the_close(
    window: Window, entry: str
) -> None:
    window.write_all({entry: _busy_after_close})
    rig = entry.split("-")[0]
    assert assemble_module().check(context(window), rig, entry) == []


def test_a_run_shaped_like_srv1_01_passes_its_recheck_where_swap_is_recorded(
    tmp_path: Path,
) -> None:
    use = use_doc(swap_recorded_not_stopped_on=["alpha"])
    window = frozen_window(tmp_path, use=use)
    window.write_all({"alpha-01": _like_srv1_01})
    assert assemble_module().check(context(window), "alpha", "alpha-01") == []


def test_room_and_the_card_peak_are_the_max_over_every_sample_up_to_idle(
    window: Window,
) -> None:
    container = hashlib.sha256(b"alpha-03").hexdigest()

    def peak_after_close(payload: dict[str, Any]) -> None:
        body = payload["doc"]["load"]["load"]
        body["samples"] = [
            f"gpu_app=4242,4000,{container},llama-server\n",
            f"gpu_app=4242,4400,{container},llama-server\n",
        ]
        body["samples_before_close"] = 1

    window.write_all({"alpha-03": peak_after_close})
    evidence, runs, lines = assemble_module().assemble(context(window))
    solo = next(c for c in evidence["combinations"] if c["slots"][0][0] == "a_solo")
    assert solo["card_peak_mib"] == {"a_solo": 4400}
    assert "  units.a_solo.room_mib: 5000 -> 4400" in lines
    load = runs["runs"]["alpha-03"]["loads"]["a_solo"]
    assert (load["peak_mib"], load["peak_before_close_mib"]) == (4400, 4000)
    assert load["sampled_until_idle"] is True
    every = [x for run in runs["runs"].values() for x in run["loads"].values()]
    assert every and all(x["sampled_until_idle"] is True for x in every)


def test_a_load_not_sampled_until_idle_is_kept_with_its_peak_a_lower_bound(
    window: Window,
) -> None:
    window.write_all({"alpha-01": _not_sampled_until_idle})
    asm = assemble_module()
    ctx = context(window)
    assert asm.check(ctx, "alpha", "alpha-01") == []
    load = asm.gather(ctx, window.runs.entry("alpha-01"))["loads"]["a_solo"]
    assert (load["sampled_until_idle"], load["peak_is_lower_bound"]) == (False, True)
    assert load["peak_mib"] == PEAK["a_solo"]


@pytest.mark.parametrize(
    ("changes", "unit"),
    [
        ({"alpha-01": _not_sampled_until_idle}, "a_solo"),
        (
            {"beta-04": _row_not_sampled_until_idle},
            "b_small",
        ),
    ],
    ids=["llamacpp", "vllm"],
)
def test_room_is_refused_while_fewer_than_k_runs_were_sampled_until_idle(
    tmp_path: Path, changes: dict[str, Any], unit: str
) -> None:
    window = frozen_window(tmp_path)
    window.write_all(changes)
    asm = assemble_module()
    with pytest.raises(asm.AssemblyRefusedError) as refused:
        asm.assemble(context(window))
    said = str(refused.value)
    assert unit in said and "sampled until idle" in said, said
    for entry in changes:
        assert entry in said, said
