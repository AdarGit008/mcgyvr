"""A sample wakes a sleeper through the ladder manager, and the lock keeps its swap.

#731 item 3: a fleet whose unit says ``role: sleeps-until-needed`` is
sampled as ONE fleet. ``mcgyvr setup`` lays the sleeper out asleep, its launch
spec leaves it down, and the sample swaps it in through the ladder manager's
own wake (:func:`mcgyvr.ladder_manager.wake_making_room`: the units
``room_for`` names are put down first), probes it exactly as it probes an awake
unit, then puts it down and wakes its room back
(:func:`mcgyvr.ladder_manager.give_back`). Each way is a move with its rig,
whether it passed, its downtime and each unit's wake time. The sample is green
only when the sleeper answered its probe and both ways passed; otherwise the
reason names the unit and the way. A green sample's evidence carries the moves,
the lock keeps them under ``swaps`` in the shape it keeps a switch's rig moves,
and ``mcgyvr fleet use`` prints them. A fleet with no sleeper samples, stamps
and locks as it always did.

The rig is :class:`tests.setup_door.FakeRig` behind the door, and the switches
are a fake that starts and stops its containers on a clock that ticks one
second per reading; which units make room is the fake's own answer, as it is
:class:`mcgyvr.wake.CardSwitches`'s on a real card. Nothing reaches a machine.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests import onedoor
from tests import setup_door as sd

FAST = "rig-s-coder-s-8081"
STRONG = "rig-s-coder-l-8082"
FAST_CONTAINER = "mcgyvr-rig-s-coder-s-8081"
STRONG_CONTAINER = "mcgyvr-rig-s-coder-l-8082"
ROOMS = {FAST: 6000, STRONG: 5000}


def _unit(port: int, container: str) -> dict[str, Any]:
    return {
        "rig": sd.RIG,
        "engine": "llama.cpp",
        "address": f"http://{sd.RIG}:{port}",
        "model": "example/Coder-GGUF",
        "width": 1,
        "window": sd.WINDOW,
        "container": container,
    }


def _staged(tmp_path: Path, *, sleeper: bool = True) -> Path:
    """A staged setup on the invented rig, laid out by the sampler's own
    :func:`~mcgyvr.fleet.sampler.lay_out`: the fast unit always on, and the
    strong one a sleeper (or, without ``sleeper``, not on the rig at all)."""
    from mcgyvr.fleet import ids, sampler
    from mcgyvr.serving import rigfile

    units = {FAST: _unit(8081, FAST_CONTAINER)}
    if sleeper:
        units[STRONG] = {
            **_unit(8082, STRONG_CONTAINER),
            "role": "sleeps-until-needed",
        }
    setup = tmp_path / "staged"
    setup.mkdir()
    (setup / "fleet.yaml").write_text(
        yaml.safe_dump({"units": units}, sort_keys=False), encoding="utf-8"
    )
    (setup / "policy.yaml").write_text(
        yaml.safe_dump(
            {
                "use_case": "coding",
                "ladder": list(units),
                "journal": {"dir": str(tmp_path / "journal")},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    rigfile.save(sd.RIG, sd.reading())
    sampler.lay_out(
        setup, {sd.RIG: ids.rig_id(onedoor.machine_reading(sd.SNAPSHOT))}, ROOMS
    )
    return setup


@dataclass
class Switches:
    """The ladder manager's switches over the fake rig: a wake starts the unit's
    container, a sleep stops it, and a call named in ``fails`` answers False and
    changes nothing."""

    rig: sd.FakeRig
    room: dict[str, tuple[str, ...]] = field(default_factory=dict)
    fails: set[tuple[str, str]] = field(default_factory=set)
    calls: list[tuple[str, str]] = field(default_factory=list)

    def _switch(self, verb: str, rung: str) -> bool:
        self.calls.append((verb, rung))
        if (verb, rung) in self.fails:
            return False
        container = {FAST: FAST_CONTAINER, STRONG: STRONG_CONTAINER}[rung]
        if verb == "wake":
            self.rig.up.add(container)
        else:
            self.rig.up.discard(container)
        return True

    def wake(self, rung: str) -> bool:
        return self._switch("wake", rung)

    def sleep(self, rung: str) -> bool:
        return self._switch("sleep", rung)

    def room_for(self, rung: str) -> tuple[str, ...]:
        return self.room.get(rung, ())

    def card_of(self, rung: str) -> tuple[str, ...]:
        return (rung,)


class Exploding:
    """Switches no sample of a fleet with no sleeper may touch."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"a fleet with no sleeper called the switches' {name}")


def _clock() -> Iterator[float]:
    return itertools.count(1.0)


@pytest.fixture
def rig(monkeypatch: pytest.MonkeyPatch) -> sd.FakeRig:
    """The fake rig behind the door, up as a whole ``serve up`` leaves it: the
    always-on unit running and the sleeper down."""
    from mcgyvr import wake

    fake = sd.FakeRig(up={FAST_CONTAINER})
    monkeypatch.setattr(wake, "spawn_door", fake)
    return fake


def _sample(setup: Path, switches: Any) -> Any:
    from mcgyvr.fleet import sampler

    clock = _clock()
    return sampler.run(
        setup,
        run_contract=sd.accepted,
        switches=switches,
        clock=lambda: next(clock),
    )


def _stamped(ran: Any) -> Any:
    from mcgyvr.fleet.stamp import stamp

    return stamp(ran.sample, run_id="sample-1")


def test_the_sampler_lays_a_sleeper_out_asleep(tmp_path: Path) -> None:
    setup = _staged(tmp_path)
    doc = yaml.safe_load((setup / "fleet.yaml").read_text(encoding="utf-8"))
    assert doc["fleets"]["own"]["layout"][sd.RIG] == [
        [FAST, "awake"],
        [STRONG, "asleep"],
    ]


def test_a_read_of_the_setup_probes_its_sleeper_and_no_other_asleep_unit(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import read

    setup = _staged(tmp_path)
    read.prepare(sd.RIG, (STRONG,), fleet_name="own", setup=setup)

    doc = yaml.safe_load((setup / "fleet.yaml").read_text(encoding="utf-8"))
    del doc["units"][STRONG]["role"]
    (setup / "fleet.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(read.ReadError, match=f"{STRONG}: not an awake unit"):
        read.prepare(sd.RIG, (STRONG,), fleet_name="own", setup=setup)


def test_a_sleeper_samples_green_through_the_switches_and_the_lock_keeps_its_swap(
    tmp_path: Path, rig: sd.FakeRig, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr import cli
    from mcgyvr.fleet.lock import write_from_stamp
    from mcgyvr.fleet.promote import promote
    from mcgyvr.fleet.stamp import SETUP_DIR

    setup = _staged(tmp_path)
    switches = Switches(rig, room={STRONG: (FAST,)})

    ran = _sample(setup, switches)

    assert switches.calls == [
        ("sleep", FAST),
        ("wake", STRONG),
        ("sleep", STRONG),
        ("wake", FAST),
    ], "in makes the room and wakes the sleeper; back puts it down and wakes the room"
    reads = [call for call in rig.calls if call[0] == "read"]
    assert reads == [
        ("read", sd.RIG, "own", (), None),
        ("read", sd.RIG, "own", (FAST,), f"1x{sd.WINDOW}"),
        ("read", sd.RIG, "own", (STRONG,), f"1x{sd.WINDOW}"),
        ("read", sd.RIG, "own", (), None),
    ], "the sleeper is probed like an awake unit, while it is in"
    assert rig.up == {FAST_CONTAINER}, "the rig is left as its layout lays it out"

    stamped = _stamped(ran)
    assert stamped.green, stamped.why
    assert stamped.folder is not None
    evidence = json.loads((stamped.folder / "evidence.json").read_text())
    laid = [[FAST, "awake"], [STRONG, "asleep"]]
    woken = [[FAST, "asleep"], [STRONG, "awake"]]
    assert evidence["moves"] == [
        {
            "rig": sd.RIG,
            "unit": STRONG,
            "way": "in",
            "from": laid,
            "to": woken,
            "passed": True,
            "downtime_s": 3.0,
            "wake_s": {STRONG: 1.0},
        },
        {
            "rig": sd.RIG,
            "unit": STRONG,
            "way": "back",
            "from": woken,
            "to": laid,
            "passed": True,
            "downtime_s": 3.0,
            "wake_s": {FAST: 1.0},
        },
    ]
    (comb,) = evidence["combinations"]
    assert set(comb["warm_decode_tok_s"]) == {FAST, STRONG}, "the sleeper's probe"

    write_from_stamp(stamped.folder)
    lock = json.loads((stamped.folder / "lock" / "own.json").read_text())
    assert lock["swaps"] == [
        {
            "rig": sd.RIG,
            "unit": STRONG,
            "way": "in",
            "downtime_s": 3.0,
            "wake_s": {STRONG: 1.0},
        },
        {
            "rig": sd.RIG,
            "unit": STRONG,
            "way": "back",
            "downtime_s": 3.0,
            "wake_s": {FAST: 1.0},
        },
    ]

    folder = promote(stamped.folder, stamped.folder / SETUP_DIR, "own")
    capsys.readouterr()
    assert cli.main(["fleet", "use", folder.name]) == 0
    out = capsys.readouterr().out
    assert f"swap: {STRONG} in on {sd.RIG}: downtime 3.0 s, wake {STRONG} 1.0 s" in out
    assert f"swap: {STRONG} back on {sd.RIG}: downtime 3.0 s, wake {FAST} 1.0 s" in out


def test_the_lock_refuses_a_sleeper_whose_swap_never_ran_in_dev(
    tmp_path: Path, rig: sd.FakeRig
) -> None:
    from mcgyvr.fleet import lock
    from mcgyvr.fleet.files import load_fleet, load_policy

    setup = _staged(tmp_path)
    stamped = _stamped(_sample(setup, Switches(rig, room={STRONG: (FAST,)})))
    assert stamped.folder is not None
    evidence = json.loads((stamped.folder / "evidence.json").read_text())
    evidence["moves"] = [m for m in evidence["moves"] if m["way"] != "back"]

    with pytest.raises(lock.LockRefusedError) as refused:
        lock.write(
            tmp_path / "elsewhere",
            load_fleet((setup / "fleet.yaml").read_text(encoding="utf-8")),
            evidence,
            policy=load_policy((setup / "policy.yaml").read_text(encoding="utf-8")),
            tolerances=lock.tolerances(),
        )
    assert f"the swap of {STRONG} on {sd.RIG}, back, never ran in dev" in str(
        refused.value
    )


class Unanswering(sd.FakeRig):
    """The fake rig, whose harness gets no answer from the sleeper."""

    def _measure(self, doc: dict[str, Any]) -> Any:
        measure = super()._measure(doc)

        def unanswered(name: str, spec: str) -> str:
            if name == STRONG:
                return json.dumps({"error": "connection refused"})
            return str(measure(name, spec))

        return unanswered


def test_a_sleeper_that_does_not_answer_its_probe_is_red_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr import wake

    fake = Unanswering(up={FAST_CONTAINER})
    monkeypatch.setattr(wake, "spawn_door", fake)
    setup = _staged(tmp_path)

    stamped = _stamped(_sample(setup, Switches(fake, room={STRONG: (FAST,)})))

    assert not stamped.green
    assert any(
        reason.startswith(f"probe: {STRONG}: warm_decode_tok_s, prefill_tok_s")
        and "connection refused" in reason
        for reason in stamped.why
    ), stamped.why
    assert not [reason for reason in stamped.why if reason.startswith("swap:")], (
        "the swap itself passed both ways"
    )


def test_a_swap_that_fails_on_the_way_back_is_red_by_way(
    tmp_path: Path, rig: sd.FakeRig
) -> None:
    setup = _staged(tmp_path)
    switches = Switches(rig, room={STRONG: (FAST,)}, fails={("wake", FAST)})

    ran = _sample(setup, switches)
    stamped = _stamped(ran)

    assert not stamped.green
    assert f"swap: {STRONG} on {sd.RIG}, back: wake {FAST} back: failed" in (
        stamped.why
    ), stamped.why
    assert not [
        r for r in stamped.why if r.startswith(f"swap: {STRONG} on {sd.RIG}, in")
    ]
    assert [(m.way, m.passed) for m in ran.sample.moves] == [
        ("in", True),
        ("back", False),
    ]


def test_a_sleeper_that_will_not_wake_gives_its_room_back_and_is_red_on_the_way_in(
    tmp_path: Path, rig: sd.FakeRig
) -> None:
    setup = _staged(tmp_path)
    switches = Switches(rig, room={STRONG: (FAST,)}, fails={("wake", STRONG)})

    stamped = _stamped(_sample(setup, switches))

    assert switches.calls == [("sleep", FAST), ("wake", STRONG), ("wake", FAST)]
    assert rig.up == {FAST_CONTAINER}
    assert f"swap: {STRONG} on {sd.RIG}, in: wake {STRONG}: failed" in stamped.why
    assert ("read", sd.RIG, "own", (STRONG,), f"1x{sd.WINDOW}") not in rig.calls, (
        "a sleeper that did not go in is not probed"
    )


def test_a_setup_that_may_not_sleep_and_wake_is_red_on_the_way_in(
    tmp_path: Path, rig: sd.FakeRig
) -> None:
    setup = _staged(tmp_path)

    stamped = _stamped(_sample(setup, None))

    assert not stamped.green
    assert any(
        reason.startswith(f"swap: {STRONG} on {sd.RIG}, in: ")
        and "does not let mcgyvr sleep and wake a unit itself" in reason
        for reason in stamped.why
    ), stamped.why


def test_a_fleet_with_no_sleeper_samples_stamps_and_locks_as_before(
    tmp_path: Path, rig: sd.FakeRig
) -> None:
    from mcgyvr.fleet.lock import write_from_stamp

    setup = _staged(tmp_path, sleeper=False)

    ran = _sample(setup, Exploding())

    assert rig.calls == [
        ("read", sd.RIG, "own", (), None),
        ("read", sd.RIG, "own", (FAST,), f"1x{sd.WINDOW}"),
        ("read", sd.RIG, "own", (), None),
    ]
    assert ran.sample.moves == ()
    stamped = _stamped(ran)
    assert stamped.green, stamped.why
    assert stamped.folder is not None
    evidence = json.loads((stamped.folder / "evidence.json").read_text())
    assert evidence["moves"] == []
    write_from_stamp(stamped.folder)
    lock = json.loads((stamped.folder / "lock" / "own.json").read_text())
    assert sorted(lock) == ["layout_sha256", "next", "switches"]
