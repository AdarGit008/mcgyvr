"""A red sample stamps nothing, and says why.

Owner, Round 4 (2026-10-07), FLEET FLOW TWEAK: sample green = fleet STAMPED;
sample red = no stamp, report why. Plan section 8.2: a lock refusal is a red
sample, reported by its own message. Round 8: until P10 lands, a plan with a
llama.cpp sleeper samples red, "the swap isn't built yet (P10)"; media-gen
waits for P11.

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
    assert done.name is None and done.promoted is None
    _nothing_stamped(None)
    said = "\n".join(done.lines())
    assert said.startswith("no stamp"), said
    return said


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(tmp_path))
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
    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(tmp_path))
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
    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(tmp_path))
    setup = fx.staged(tmp_path)
    _read_twice(setup)
    said = _red(setup, _sample(setup))
    assert "rig file" in said and fx.RIG in said, said


def test_a_sleeper_is_red_until_the_swap_is_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(tmp_path))
    fx.rig_file()
    setup = fx.staged(tmp_path, fleet=fx.fleet_doc(asleep=True))
    fx.read(setup, fx.READS[0], text=fx.reader_text(strong=True))
    fx.read(setup, fx.READS[1], text=fx.reader_text(strong=True), load=None)

    said = _red(setup, _sample(setup))

    assert fx.STRONG in said and "the swap isn't built yet (P10)" in said, said


def test_a_media_gen_sample_is_red_until_it_is_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(tmp_path))
    fx.rig_file()
    setup = fx.staged(tmp_path, policy=fx.policy_doc(tmp_path, "media-gen"))
    _read_twice(setup)
    said = _red(setup, _sample(setup))
    assert "media-gen" in said and "P11" in said, said


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

    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(tmp_path))
    fx.rig_file()
    setup = fx.staged(tmp_path, policy=fx.policy_doc(tmp_path, "chat"))
    _read_twice(setup)
    outcome = sample.Outcome("completion", unit=fx.UNIT, passed=True, served=served)

    said = _red(setup, _sample(setup, (outcome,)))

    assert fx.UNIT in said and word in said, said


def test_an_agent_sample_needs_both_grounded_and_safety(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.fleet import sample

    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(tmp_path))
    fx.rig_file()
    setup = fx.staged(tmp_path, policy=fx.policy_doc(tmp_path, "agent"))
    _read_twice(setup)
    outcomes = (
        sample.Outcome("grounded", unit=fx.UNIT, passed=True),
        sample.Outcome("safety", unit=fx.UNIT, passed=False, why="leaked a key"),
    )
    said = _red(setup, _sample(setup, outcomes))
    assert "safety" in said and "leaked a key" in said, said


@pytest.mark.parametrize(("label", "probability"), [("", 0.5), ("b", 1.5), ("b", None)])
def test_an_opted_in_jev_that_gives_no_valid_choice_is_red(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    probability: float | None,
) -> None:
    from mcgyvr.fleet import sample

    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(tmp_path))
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


def test_a_lock_refusal_is_red_by_the_locks_own_message(setup: Path) -> None:
    """The reads name another rig than the one the staged setup pins."""
    moved = {**fx.SNAPSHOT, "driver": "501.00"}
    fx.read(setup, fx.READS[0], text=fx.reader_text(snapshot=moved))
    fx.read(setup, fx.READS[1], text=fx.reader_text(snapshot=moved), load=None)

    said = _red(setup, _sample(setup))

    assert "lock" in said and fx.rig_id(moved) in said, said


def test_a_second_stamp_of_the_same_lock_is_red_and_keeps_the_first(
    setup: Path,
) -> None:
    from mcgyvr.fleet import stamp
    from mcgyvr.fleet.roots import data_home, fleets_dir, live_file

    _read_twice(setup)
    first = stamp.stamp(_sample(setup), run_id="sample-1")
    assert first.green, first.why
    live = live_file().read_bytes()

    again = stamp.stamp(_sample(setup), run_id="sample-2")

    assert not again.green
    said = "\n".join(again.lines())
    assert "already exists" in said, said
    assert [p.name for p in fleets_dir().iterdir()] == [first.name]
    assert live_file().read_bytes() == live
    assert not (data_home() / "stamps" / fx.FLEET / "sample-2").exists()


def test_a_run_id_already_stamped_is_red(setup: Path) -> None:
    from mcgyvr.fleet import stamp

    _read_twice(setup)
    assert stamp.stamp(_sample(setup), run_id="sample-1").green
    again = stamp.stamp(_sample(setup), run_id="sample-1")
    assert not again.green
    assert "sample-1" in "\n".join(again.lines())


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
