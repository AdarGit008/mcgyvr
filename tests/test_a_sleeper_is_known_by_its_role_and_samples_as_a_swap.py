"""A sleeper is known by its role, and its swap is stamped as two fleets.

Owner, Round 8 (P7b, after P10 landed): a unit that sleeps until needed is
``units.<u>.role: sleeps-until-needed`` -- not an ``asleep`` slot -- and a
llama.cpp sleeper is no longer red "swap isn't built yet". Its swap is stamped
as two fleets, F and F-strong, each listed in the other's ``next``: the strong
rung takes its partner's slot in F-strong (a llama.cpp sleep frees the room,
and a freed room is a free slot, ``fleet-identity.md`` ID-4). Plan section
8.2: the sample wakes the strong unit and sleeps it back, and both moves,
with their downtime and wake seconds, are the evidence's ``moves``.

Promises:

* a swap whose two fleets were read and whose two moves passed is stamped:
  F and F-strong are both promoted, F is named live, and F's lock lists the
  switch to F-strong with the move the sample measured;
* a sleeper no fleet in F's ``next`` wakes, a move that did not run, and a
  move that failed are each red, by the unit or the move;
* an ``asleep`` slot of a unit that states no role is not a reason by itself.

No rig is reached: the rig is invented and its reads are canned.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests import sample_fleet as fx

SAMPLE_DAY = fx.SAMPLE_DAY


def _moves(*, back: bool = True, passed: bool = True) -> tuple[Any, ...]:
    from mcgyvr.fleet import sample

    there = sample.Move(
        rig=fx.RIG,
        from_fleet=fx.FLEET,
        to_fleet=fx.STRONG_FLEET,
        passed=passed,
        downtime_s=31.5,
        wake_s=24.0,
        why="" if passed else "the strong rung never answered",
    )
    home = sample.Move(
        rig=fx.RIG,
        from_fleet=fx.STRONG_FLEET,
        to_fleet=fx.FLEET,
        passed=True,
        downtime_s=12.0,
        wake_s=9.5,
    )
    return (there, home) if back else (there,)


def _sample(setup: Path, moves: Any = None, **more: Any) -> Any:
    from mcgyvr.fleet import sample

    return sample.Sample(
        setup=setup,
        fleet=fx.FLEET,
        reads=(*fx.READS, *fx.STRONG_READS),
        outcomes=(sample.Outcome("gate", unit=fx.UNIT, passed=True),),
        moves=_moves() if moves is None else moves,
        **more,
    )


@pytest.fixture
def swap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A staged swap, both its fleets read the way the sample reads them."""
    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(tmp_path))
    fx.rig_file()
    setup = fx.staged(
        tmp_path, fleet=fx.swap_doc(), policy=fx.swap_policy(tmp_path)
    )
    fx.read(setup, fx.READS[0])
    fx.read(setup, fx.READS[1], load=None)
    fx.read_strong(setup, fx.STRONG_READS[0])
    fx.read_strong(setup, fx.STRONG_READS[1], load=None)
    return setup


def test_a_swap_with_both_moves_measured_stamps_the_fleet_and_its_strong_partner(
    swap: Path,
) -> None:
    from mcgyvr.fleet import sample, stamp
    from mcgyvr.fleet.promote import LOCK_DIR
    from mcgyvr.fleet.roots import fleets_dir, live_file

    verdict = sample.judge(_sample(swap))
    assert verdict.green, verdict.why
    evidence = verdict.evidence
    assert evidence is not None
    slots = {
        tuple(map(tuple, comb["slots"])): comb for comb in evidence["combinations"]
    }
    assert set(slots) == {((fx.UNIT, "awake"),), ((fx.STRONG, "awake"),)}
    strong = slots[((fx.STRONG, "awake"),)]
    assert strong["warm_decode_tok_s"] == {fx.STRONG: 12.5}
    assert strong["card_peak_mib"] == {fx.STRONG: 4700}
    assert evidence["moves"] == [
        {
            "rig": fx.RIG,
            "from": [[fx.UNIT, "awake"]],
            "to": [[fx.STRONG, "awake"]],
            "passed": True,
            "downtime_s": 31.5,
            "wake_s": 24.0,
        },
        {
            "rig": fx.RIG,
            "from": [[fx.STRONG, "awake"]],
            "to": [[fx.UNIT, "awake"]],
            "passed": True,
            "downtime_s": 12.0,
            "wake_s": 9.5,
        },
    ]

    done = stamp.stamp(_sample(swap), run_id="sample-1")

    assert done.green, done.why
    promoted = sorted(p.name for p in fleets_dir().iterdir())
    assert promoted == sorted(
        [f"{fx.FLEET}@{SAMPLE_DAY}", f"{fx.STRONG_FLEET}@{SAMPLE_DAY}"]
    )
    assert json.loads(live_file().read_text(encoding="utf-8"))["fleet"] == (
        f"{fx.FLEET}@{SAMPLE_DAY}"
    )
    lock = json.loads(
        (done.folder / LOCK_DIR / f"{fx.FLEET}.json").read_text(encoding="utf-8")
    )
    assert lock["next"] == [fx.STRONG_FLEET]
    assert lock["switches"] == [
        {
            "to": fx.STRONG_FLEET,
            "moves": [{"rig": fx.RIG, "downtime_s": 31.5, "wake_s": 24.0}],
        }
    ]
    said = "\n".join(done.lines())
    assert f"{fx.STRONG_FLEET}@{SAMPLE_DAY}" in said, said


def test_a_sleeper_no_fleet_wakes_is_red_by_its_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.fleet import sample

    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(tmp_path))
    fx.rig_file()
    doc = fx.swap_doc()
    del doc["fleets"][fx.STRONG_FLEET]
    doc["fleets"][fx.FLEET]["next"] = []
    setup = fx.staged(tmp_path, fleet=doc, policy=fx.swap_policy(tmp_path))
    fx.read(setup, fx.READS[0])
    fx.read(setup, fx.READS[1], load=None)

    verdict = sample.judge(_sample(setup, moves=()))

    assert not verdict.green
    said = "\n".join(verdict.why)
    assert fx.STRONG in said and "sleeps until needed" in said, said
    assert "P10" not in said, "the swap is built: it is no longer the reason"


def test_a_swap_whose_way_back_did_not_run_is_red(swap: Path) -> None:
    from mcgyvr.fleet import sample

    verdict = sample.judge(_sample(swap, moves=_moves(back=False)))

    assert not verdict.green
    said = "\n".join(verdict.why)
    assert f"{fx.STRONG_FLEET} → {fx.FLEET}" in said and "did not run" in said, said


def test_a_swap_move_that_failed_is_red_by_its_reason(swap: Path) -> None:
    from mcgyvr.fleet import stamp

    done = stamp.stamp(_sample(swap, moves=_moves(passed=False)), run_id="sample-1")

    assert not done.green
    said = "\n".join(done.lines())
    assert f"{fx.FLEET} → {fx.STRONG_FLEET}" in said, said
    assert "the strong rung never answered" in said, said


def test_a_strong_fleet_that_was_not_read_is_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.fleet import sample

    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(tmp_path))
    fx.rig_file()
    setup = fx.staged(
        tmp_path, fleet=fx.swap_doc(), policy=fx.swap_policy(tmp_path)
    )
    fx.read(setup, fx.READS[0])
    fx.read(setup, fx.READS[1], load=None)

    verdict = sample.judge(_sample(setup))

    assert not verdict.green
    said = "\n".join(verdict.why)
    assert fx.STRONG_FLEET in said and "read" in said, said


def test_an_asleep_slot_with_no_role_is_not_a_reason_by_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.fleet import sample

    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(tmp_path))
    fx.rig_file()
    setup = fx.staged(tmp_path, fleet=fx.fleet_doc(asleep=True))
    fx.read(setup, fx.READS[0], text=fx.reader_text(strong=True))
    fx.read(setup, fx.READS[1], text=fx.reader_text(strong=True), load=None)

    verdict = sample.judge(_sample(setup, moves=()))

    assert not any("swap" in reason for reason in verdict.why), verdict.why
