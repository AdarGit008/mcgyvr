"""A red sample stamps nothing, and says why.

Sample green = fleet STAMPED;
sample red = no stamp, report why. A sleeper whose swap through the ladder
manager did not run samples red, named with the way it did not go
(``test_a_sample_wakes_a_sleeper_through_the_ladder_manager_and_locks_its_swap.py``
has the swap that did). A stamp locks nothing, so a lock's refusal of a stamp
is :func:`mcgyvr.fleet.lock.write_from_stamp`'s to report
(``test_a_stamp_writes_no_lock_and_the_lock_is_written_from_the_stamp.py``).

"Stamps nothing" is checked on disk: no promoted folder, no ``live.json``
written or changed, and no stamp folder left under the data folder. The reason
names the check, the unit and what went wrong.

No rig is reached: the rig is invented and its reads are canned.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests import sample_fleet as fx


def _sample(setup: Path, outcomes: Any = None, **more: Any) -> Any:
    from mcgyvr.fleet import sample

    if outcomes is None:
        outcomes = (sample.Outcome("gate", unit=fx.UNIT, passed=True),)
    return sample.Sample(
        setup=setup, fleet=fx.FLEET, reads=fx.READS, outcomes=outcomes, **more
    )


def _read_twice(setup: Path, **first: Any) -> None:
    fx.read(setup, fx.READS[0], **first)
    fx.read(setup, fx.READS[1], load=None)


def _nothing_stamped(before_live: bytes | None) -> None:
    from mcgyvr.fleet.roots import data_home, fleets_dir, live_file

    promoted = sorted(fleets_dir().iterdir()) if fleets_dir().exists() else []
    assert promoted == [], f"a red sample promoted {promoted}"
    now = live_file().read_bytes() if live_file().exists() else None
    assert now == before_live, "a red sample touched live.json"
    stamps = data_home() / "stamps"
    left = sorted(p.as_posix() for p in stamps.rglob("*")) if stamps.exists() else []
    assert left == [] or all(Path(p).is_dir() for p in left), (
        f"a red sample left files under the stamps folder: {left}"
    )


def _red(setup: Path, sample_: Any) -> str:
    from mcgyvr.fleet import stamp

    done = stamp.stamp(sample_, run_id="sample-1")
    assert not done.green, "a red sample was stamped"
    assert done.folder is None
    _nothing_stamped(None)
    said = "\n".join(done.lines())
    assert said.startswith("no stamp"), said
    return said


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fx.rig_file()
    return fx.staged(tmp_path)


def test_a_gate_that_fails_on_every_rung_is_red_with_each_rungs_reason(
    setup: Path,
) -> None:
    from mcgyvr.fleet import sample

    _read_twice(setup)
    said = _red(
        setup,
        _sample(
            setup,
            (
                sample.Outcome(
                    "gate", unit=fx.UNIT, passed=False, why="2 of 3 tests failed"
                ),
            ),
        ),
    )
    assert "gate" in said and fx.UNIT in said and "2 of 3 tests failed" in said


def test_a_use_case_task_that_did_not_run_is_red(setup: Path) -> None:
    _read_twice(setup)
    said = _red(setup, _sample(setup, outcomes=()))
    assert "gate" in said and "did not run" in said, said


def test_a_probe_the_harness_could_not_take_is_red_with_the_reads_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fx.rig_file()
    setup = fx.staged(tmp_path)
    fx.read(setup, fx.READS[0], harness=fx.Harness(fails="connection refused"))
    fx.read(setup, fx.READS[1], harness=fx.Harness(fails="connection refused"))

    said = _red(setup, _sample(setup))

    assert fx.UNIT in said and "warm_decode_tok_s" in said, said
    assert "connection refused" in said, "the read's own failure is the reason"


def test_a_unit_that_restarted_is_red(setup: Path) -> None:
    _read_twice(setup, text=fx.reader_text(restarts="2"))
    said = _red(setup, _sample(setup))
    assert fx.UNIT in said and "restart" in said, said


def test_a_rig_with_no_read_is_red(setup: Path) -> None:
    said = _red(setup, _sample(setup))
    assert fx.RIG in said and "read" in said, said


def test_a_rig_with_no_rig_file_is_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = fx.staged(tmp_path)
    _read_twice(setup)
    said = _red(setup, _sample(setup))
    assert "rig file" in said and fx.RIG in said, said


def test_a_sleeper_whose_swap_did_not_run_is_red_by_name_and_way(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fx.rig_file()
    setup = fx.staged(tmp_path, fleet=fx.fleet_doc(asleep=True))
    fx.read(setup, fx.READS[0], text=fx.reader_text(strong=True))
    fx.read(setup, fx.READS[1], text=fx.reader_text(strong=True), load=None)

    said = _red(setup, _sample(setup))

    assert f"swap: {fx.STRONG} on {fx.RIG}, in: did not run" in said, said
    assert f"probe: {fx.STRONG}:" in said, "a sleeper is held to its probe too"


def test_a_unit_laid_out_asleep_that_is_no_sleeper_is_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fx.rig_file()
    doc = fx.fleet_doc(asleep=True)
    del doc["units"][fx.STRONG]["role"]
    setup = fx.staged(tmp_path, fleet=doc)
    fx.read(setup, fx.READS[0], text=fx.reader_text(strong=True))
    fx.read(setup, fx.READS[1], text=fx.reader_text(strong=True), load=None)

    said = _red(setup, _sample(setup))

    assert fx.STRONG in said and "no sample wakes it" in said, said


@pytest.mark.parametrize(
    ("served", "word"),
    [
        ({"window": 4096, "slots": 4}, "window"),
        ({"window": 8192, "slots": 2}, "slots"),
        ({}, "window"),
    ],
)
def test_a_chat_unit_serving_other_than_planned_is_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, served: dict[str, int], word: str
) -> None:
    from mcgyvr.fleet import sample

    fx.rig_file()
    setup = fx.staged(tmp_path, policy=fx.policy_doc(tmp_path, "chat"))
    _read_twice(setup)
    outcome = sample.Outcome("completion", unit=fx.UNIT, passed=True, served=served)

    said = _red(setup, _sample(setup, (outcome,)))

    assert fx.UNIT in said and word in said, said


def test_an_agent_sample_whose_reply_is_not_grounded_is_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.fleet import sample

    fx.rig_file()
    setup = fx.staged(tmp_path, policy=fx.policy_doc(tmp_path, "agent"))
    _read_twice(setup)
    outcomes = (
        sample.Outcome("grounded", unit=fx.UNIT, passed=False, why="cites nothing"),
    )
    said = _red(setup, _sample(setup, outcomes))
    assert "grounded" in said and "cites nothing" in said, said


@pytest.mark.parametrize(("label", "probability"), [("", 0.5), ("b", 1.5), ("b", None)])
def test_an_opted_in_jev_that_gives_no_valid_choice_is_red(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    probability: float | None,
) -> None:
    from mcgyvr.fleet import sample

    fx.rig_file()
    policy = fx.policy_doc(tmp_path)
    policy["jev"] = {"unit": fx.UNIT}
    setup = fx.staged(tmp_path, policy=policy)
    _read_twice(setup)
    outcomes = (
        sample.Outcome("gate", unit=fx.UNIT, passed=True),
        sample.Outcome(
            "choice", unit=fx.UNIT, passed=True, label=label, probability=probability
        ),
    )
    said = _red(setup, _sample(setup, outcomes))
    assert "jev" in said.lower() or "choice" in said, said


def test_a_red_verdict_keeps_its_evidence_unpassed_for_the_report(setup: Path) -> None:
    from mcgyvr.fleet import sample

    _read_twice(setup)
    verdict = sample.judge(
        _sample(setup, (sample.Outcome("gate", unit=fx.UNIT, passed=False),))
    )
    assert not verdict.green
    assert verdict.evidence is not None
    assert verdict.evidence["combinations"][0]["passed"] is False
    json.dumps(verdict.evidence)
