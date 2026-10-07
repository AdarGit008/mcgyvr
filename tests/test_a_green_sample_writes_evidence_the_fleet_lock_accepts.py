"""A green sample writes evidence the fleet lock accepts, and the fleet is stamped.

Owner, Round 4 (2026-10-07): the owner's confirm is approval to run the
SAMPLE -- start the servers and run the sample check task. A green sample is
the fleet STAMPED: approved, locked, reusable through ``fleet use``. Plan
section 8.2: the sample's results are written as the dev-run evidence JSON
``fleet lock`` already reads, then the existing chain runs unchanged -- ``fleet
lock`` -> ``fleet promote`` -> ``fleet use``.

* **The evidence is read from the door's own read rows** (P7a, Round 8):
  ``read --fleet F --probe U --load WxN`` of the staged setup files the
  snapshot (the rig id, the card's reserve as the combination's overhead),
  each unit's card and restarts, the probe's warm decode and prefill, and the
  load's card peak. The card's size is the rig file the user's scan saved.
* **The stamp needs no lab file.** Its dev lock is written under
  ``<data folder>/stamps/<fleet>/<run_id>/`` (setup, evidence.json,
  records/fleet), promote reads from there, and the run root is not touched.

No rig is reached: the rig is invented and its reads are canned.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests import sample_fleet as fx


def _sample(setup: Path, **more: Any) -> Any:
    from mcgyvr.fleet import sample

    outcomes = more.pop(
        "outcomes",
        (sample.Outcome("gate", unit=fx.UNIT, passed=True, why="the gate passed"),),
    )
    return sample.Sample(
        setup=setup, fleet=fx.FLEET, reads=fx.READS, outcomes=outcomes, **more
    )


def _read_twice(setup: Path) -> None:
    fx.read(setup, fx.READS[0], text=fx.reader_text(card_mib=5350))
    fx.read(setup, fx.READS[1], text=fx.reader_text(card_mib=5400), load=None)


@pytest.fixture
def no_lab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A run root that holds no lab file, and must stay empty."""
    root = tmp_path / "no-lab-root"
    root.mkdir()
    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(root))
    return root


def test_the_evidence_is_the_dev_run_evidence_from_the_reads_and_the_rig_file(
    tmp_path: Path, no_lab: Path
) -> None:
    from mcgyvr.fleet import sample

    setup = fx.staged(tmp_path)
    fx.rig_file()
    _read_twice(setup)

    verdict = sample.judge(_sample(setup))

    assert verdict.green, verdict.why
    evidence = verdict.evidence
    assert evidence is not None
    assert evidence["rigs"] == {fx.RIG: {"card_mib": 12288, "snapshot": fx.SNAPSHOT}}, (
        "the card is the rig file's, the snapshot the last read's"
    )
    assert evidence["moves"] == []
    (comb,) = evidence["combinations"]
    assert comb["rig"] == fx.RIG
    assert comb["slots"] == [[fx.UNIT, "awake"]], "the layout's own slots"
    assert comb["passed"] is True
    assert comb["overhead_mib"] == 310, "the snapshot's card reserve"
    assert comb["restarts"] == {fx.UNIT: 0}
    assert comb["warm_decode_tok_s"] == {fx.UNIT: 41.5}
    assert comb["prefill_tok_s"] == {fx.UNIT: 900.0}
    assert comb["card_peak_mib"] == {fx.UNIT: 5600}, (
        "the highest card reading around the sample: the load's peak"
    )
    assert comb["card_steady_mib"] == {fx.UNIT: 5400}, "the last read's card"
    assert comb["validated_at"] == "2026-10-05T10:01:00Z", "the last read's moment"


def test_the_fleet_lock_accepts_the_evidence_as_it_is(
    tmp_path: Path, no_lab: Path
) -> None:
    from mcgyvr.derived import class_tolerances
    from mcgyvr.fleet import lock, sample
    from mcgyvr.fleet.files import load_fleet, load_policy

    setup = fx.staged(tmp_path)
    fx.rig_file()
    _read_twice(setup)
    verdict = sample.judge(_sample(setup))
    assert verdict.evidence is not None

    root = tmp_path / "elsewhere"
    lock.write(
        root,
        load_fleet((setup / "fleet.yaml").read_text(encoding="utf-8")),
        json.loads(json.dumps(verdict.evidence)),
        policy=load_policy((setup / "policy.yaml").read_text(encoding="utf-8")),
        tolerances={"warm_decode_class_pct": class_tolerances()["warm_decode_tok_s"]},
    )
    assert (root / "records" / "fleet" / f"{fx.FLEET}.json").is_file()


def test_a_green_sample_is_locked_promoted_and_named_live(
    tmp_path: Path, no_lab: Path
) -> None:
    from mcgyvr.fleet import stamp
    from mcgyvr.fleet.roots import data_home, fleets_dir, live_fleet

    setup = fx.staged(tmp_path)
    fx.rig_file()
    _read_twice(setup)

    done = stamp.stamp(_sample(setup), run_id="sample-1")

    assert done.green, done.why
    assert done.name == f"{fx.FLEET}@{fx.SAMPLE_DAY}", "dated by the lock's own day"
    assert done.promoted == fleets_dir() / done.name
    assert (done.promoted / "fleet.yaml").is_file()
    assert live_fleet() == done.name, "the stamped fleet is the live one"
    folder = data_home() / "stamps" / fx.FLEET / "sample-1"
    assert done.folder == folder
    assert (folder / "setup" / "fleet.yaml").is_file()
    assert (folder / "setup" / "policy.yaml").is_file()
    assert (
        json.loads((folder / "evidence.json").read_text(encoding="utf-8"))[
            "combinations"
        ][0]["passed"]
        is True
    )
    assert (folder / "records" / "fleet" / f"{fx.FLEET}.json").is_file()
    assert os.listdir(no_lab) == [], "a stamp writes nothing under the run root"
    said = "\n".join(done.lines())
    assert f"stamped: {done.name}" in said, said


def test_a_rig_of_several_cards_is_held_to_each_card(
    tmp_path: Path, no_lab: Path
) -> None:
    from mcgyvr.fleet import sample, stamp

    fleet = fx.fleet_doc()
    fleet["units"][fx.UNIT]["launch"] = {"shards": [{"rig": fx.RIG, "gpu": 1}]}
    setup = fx.staged(tmp_path, fleet=fleet)
    fx.rig_file(cards=(12288, 8192))
    _read_twice(setup)

    verdict = sample.judge(_sample(setup))
    assert verdict.evidence is not None
    assert verdict.evidence["rigs"][fx.RIG]["cards"] == {"0": 12288, "1": 8192}
    assert "card_mib" not in verdict.evidence["rigs"][fx.RIG]

    done = stamp.stamp(_sample(setup), run_id="sample-2")
    assert done.green, done.why


@pytest.mark.parametrize(
    ("use_case", "outcomes"),
    [
        ("coding", (("gate", fx.UNIT, False), ("gate", "rig-a-other", True))),
        ("chat", (("completion", fx.UNIT, True),)),
        ("agent", (("grounded", fx.UNIT, True), ("safety", fx.UNIT, True))),
    ],
)
def test_each_use_case_is_green_by_its_own_task(
    tmp_path: Path,
    no_lab: Path,
    use_case: str,
    outcomes: tuple[tuple[str, str, bool], ...],
) -> None:
    """Coding: the gate passes on any rung. Chat: each unit answers at its
    planned window and slots. Agent: grounded and safety both pass."""
    from mcgyvr.fleet import sample

    setup = fx.staged(tmp_path, policy=fx.policy_doc(tmp_path, use_case))
    fx.rig_file()
    _read_twice(setup)
    built = tuple(
        sample.Outcome(
            check,
            unit=name,
            passed=passed,
            why="",
            served={"window": 8192, "slots": 4} if check == "completion" else {},
        )
        for check, name, passed in outcomes
    )

    verdict = sample.judge(_sample(setup, outcomes=built))

    assert verdict.green, verdict.why


def test_an_opted_in_jev_answers_one_typed_choice(tmp_path: Path, no_lab: Path) -> None:
    from mcgyvr.fleet import sample

    policy = fx.policy_doc(tmp_path)
    policy["jev"] = {"unit": fx.UNIT}
    setup = fx.staged(tmp_path, policy=policy)
    fx.rig_file()
    _read_twice(setup)
    outcomes = (
        sample.Outcome("gate", unit=fx.UNIT, passed=True),
        sample.Outcome(
            "choice", unit=fx.UNIT, passed=True, label="b", probability=0.82
        ),
    )

    verdict = sample.judge(_sample(setup, outcomes=outcomes))

    assert verdict.green, verdict.why
